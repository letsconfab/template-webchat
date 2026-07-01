"""Durability and idempotency tests for tester email notifications."""

from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.database import Base, get_db
from backend.models import diagnostics, invite  # noqa: F401
from backend.models.chat import ChatSession
from backend.models.feedback_case import (
    CaseNotification,
    CaseReply,
    FeedbackCase,
)
from backend.models.settings import SystemSettings
from backend.models.user import User
from backend.models.wiki import ChatMessage, UserFeedback
from backend.routers import (
    admin_feedback_cases,
    case_notifications,
    feedback_cases,
)
from backend.services.auth import create_access_token
from backend.services.case_notifications import case_notification_service
from backend.services.redaction import project_text


class CaseNotificationApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        database = Path(cls.tempdir.name) / "notifications.db"
        cls.engine = create_async_engine(f"sqlite+aiosqlite:///{database}")

        @event.listens_for(cls.engine.sync_engine, "connect")
        def enable_foreign_keys(connection, _record) -> None:
            connection.execute("PRAGMA foreign_keys=ON")

        cls.sessions = async_sessionmaker(cls.engine, expire_on_commit=False)
        cls.case_id = asyncio.run(cls._seed())
        app = FastAPI()
        app.include_router(feedback_cases.router)
        app.include_router(admin_feedback_cases.router)
        app.include_router(case_notifications.router)

        async def override_db():
            async with cls.sessions() as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        cls.client = TestClient(app)
        cls.original_transport = case_notification_service.transport
        cls.original_attempt = case_notification_service.attempt

    @classmethod
    async def _seed(cls) -> str:
        async with cls.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with cls.sessions() as session:
            owner = User(
                id=401,
                email="tester@example.test",
                password_hash="hash",
                role="user",
                is_active=True,
            )
            admin = User(
                id=402,
                email="admin@example.test",
                password_hash="hash",
                role="admin",
                is_active=True,
            )
            settings = SystemSettings(
                is_configured=True,
                app_name="Test WebChat",
                smtp_server="smtp.example.test",
                smtp_port=587,
                smtp_username="smtp-user",
                smtp_password="smtp-password",
                from_email="noreply@example.test",
                use_tls=True,
                frontend_url="https://chat.example.test",
                session_timeout_minutes=30,
                max_login_attempts=5,
                email_notifications_enabled=True,
                user_registration_enabled=True,
                llm_provider="openai",
                llm_model="model",
                rag_provider="openai",
                rag_model="model",
                google_drive_enabled=False,
                neo4j_url="bolt://localhost",
                neo4j_user="neo4j",
                neo4j_database="neo4j",
                cocoindex_embedding_model="test",
                graphrag_enabled=False,
            )
            chat_session = ChatSession(
                client_uuid=str(uuid4()),
                user_id=owner.id,
                ownership_state="owned",
            )
            session.add_all([owner, admin, settings, chat_session])
            await session.flush()
            answer = ChatMessage(
                chat_session_id=chat_session.id,
                session_id=chat_session.client_uuid,
                role="assistant",
                content="SECRET chat content",
            )
            session.add(answer)
            await session.flush()
            feedback = UserFeedback(
                user_id=owner.id,
                feedback_type="thumbs_down",
                rating=1,
                message="SECRET feedback content",
                chat_message_id=answer.id,
            )
            session.add(feedback)
            await session.flush()
            case = FeedbackCase(
                public_id=str(uuid4()),
                feedback_id=feedback.id,
                user_id=owner.id,
                chat_session_id=chat_session.id,
                rated_message_id=answer.id,
                status="awaiting_admin",
            )
            session.add(case)
            await session.flush()
            await project_text(
                session,
                content_type="feedback",
                content_id=feedback.id,
                source_field="message",
                raw_text=feedback.message,
            )
            await session.commit()
            return case.public_id

    @classmethod
    def tearDownClass(cls) -> None:
        case_notification_service.transport = cls.original_transport
        case_notification_service.attempt = cls.original_attempt
        asyncio.run(cls.engine.dispose())
        cls.tempdir.cleanup()

    def setUp(self) -> None:
        case_notification_service.transport = self.original_transport
        case_notification_service.attempt = self.original_attempt

        async def reset() -> None:
            async with self.sessions() as session:
                await session.execute(delete(CaseReply))
                case = (
                    await session.execute(
                        select(FeedbackCase).where(
                            FeedbackCase.public_id == self.case_id
                        )
                    )
                ).scalar_one()
                case.status = "awaiting_admin"
                settings = (
                    await session.execute(select(SystemSettings))
                ).scalar_one()
                settings.email_notifications_enabled = True
                await session.commit()

        asyncio.run(reset())

    @staticmethod
    def headers(user_id: int) -> dict[str, str]:
        return {
            "Authorization": "Bearer "
            + create_access_token({"sub": str(user_id)})
        }

    def test_success_commits_before_send_and_email_is_generic(self) -> None:
        deliveries = []

        async def transport(**kwargs) -> None:
            async with self.sessions() as session:
                case = (
                    await session.execute(
                        select(FeedbackCase).where(
                            FeedbackCase.public_id == self.case_id
                        )
                    )
                ).scalar_one()
                replies = list((await session.execute(select(CaseReply))).scalars())
                notifications = list(
                    (await session.execute(select(CaseNotification))).scalars()
                )
                self.assertEqual(case.status, "awaiting_user")
                self.assertEqual(len(replies), 1)
                self.assertEqual(len(notifications), 1)
            deliveries.append(kwargs)

        case_notification_service.transport = transport
        created = self.client.post(
            f"/api/admin/feedback-cases/{self.case_id}/replies",
            json={"text": "SECRET admin reply"},
            headers=self.headers(402),
        )

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["notification"]["state"], "sent")
        self.assertEqual(len(deliveries), 1)
        delivery = deliveries[0]
        self.assertEqual(delivery["recipient"], "tester@example.test")
        self.assertIn("Test WebChat", delivery["subject"])
        self.assertIn(
            f"https://chat.example.test/feedback/{self.case_id}",
            delivery["body"],
        )
        for forbidden in (
            "SECRET admin reply",
            "SECRET feedback content",
            "SECRET chat content",
        ):
            self.assertNotIn(forbidden, delivery["body"])

        notification_id = created.json()["notification"]["id"]
        retry = self.client.post(
            f"/api/admin/case-notifications/{notification_id}/retry",
            headers=self.headers(402),
        )
        self.assertEqual(retry.json()["state"], "sent")
        self.assertEqual(retry.json()["attempt_count"], 1)
        self.assertEqual(len(deliveries), 1)

    def test_timeout_fails_without_rollback_then_retry_succeeds(self) -> None:
        case_notification_service.transport = AsyncMock(
            side_effect=TimeoutError("timeout")
        )
        created = self.client.post(
            f"/api/admin/feedback-cases/{self.case_id}/replies",
            json={"text": "Admin reply"},
            headers=self.headers(402),
        )
        self.assertEqual(created.json()["notification"]["state"], "failed")
        self.assertEqual(
            created.json()["notification"]["safe_error_category"],
            "timeout",
        )

        case_notification_service.transport = AsyncMock(return_value=None)
        notification_id = created.json()["notification"]["id"]
        retry = self.client.post(
            f"/api/admin/case-notifications/{notification_id}/retry",
            headers=self.headers(402),
        )
        self.assertEqual(retry.json()["state"], "sent")
        self.assertEqual(retry.json()["attempt_count"], 2)

        owner_case = self.client.get(
            f"/api/feedback-cases/{self.case_id}",
            headers=self.headers(401),
        )
        self.assertEqual(owner_case.json()["status"], "awaiting_user")
        self.assertEqual(owner_case.json()["replies"][-1]["text"], "Admin reply")

    def test_interruption_leaves_pending_notification_for_retry(self) -> None:
        case_notification_service.attempt = AsyncMock(
            side_effect=RuntimeError("process interrupted")
        )
        created = self.client.post(
            f"/api/admin/feedback-cases/{self.case_id}/replies",
            json={"text": "Committed first"},
            headers=self.headers(402),
        )
        self.assertEqual(created.json()["notification"]["state"], "pending")

        case_notification_service.attempt = self.original_attempt
        case_notification_service.transport = AsyncMock(return_value=None)
        notification_id = created.json()["notification"]["id"]
        retried = self.client.post(
            f"/api/admin/case-notifications/{notification_id}/retry",
            headers=self.headers(402),
        )
        self.assertEqual(retried.json()["state"], "sent")

    def test_disabled_configuration_is_visible_and_other_actions_send_nothing(self) -> None:
        async def disable() -> None:
            async with self.sessions() as session:
                settings = (
                    await session.execute(select(SystemSettings))
                ).scalar_one()
                settings.email_notifications_enabled = False
                await session.commit()

        asyncio.run(disable())
        transport = AsyncMock(return_value=None)
        case_notification_service.transport = transport
        created = self.client.post(
            f"/api/admin/feedback-cases/{self.case_id}/replies",
            json={"text": "Admin reply"},
            headers=self.headers(402),
        )
        self.assertEqual(created.json()["notification"]["state"], "failed")
        self.assertEqual(
            created.json()["notification"]["safe_error_category"],
            "disabled_configuration",
        )
        transport.assert_not_awaited()

        self.client.post(
            f"/api/feedback-cases/{self.case_id}/replies",
            json={"text": "User reply"},
            headers=self.headers(401),
        )
        self.client.post(
            f"/api/admin/feedback-cases/{self.case_id}/resolve",
            headers=self.headers(402),
        )

        async def notification_count() -> int:
            async with self.sessions() as session:
                return len(
                    list(
                        (
                            await session.execute(select(CaseNotification))
                        ).scalars()
                    )
                )

        self.assertEqual(asyncio.run(notification_count()), 1)


if __name__ == "__main__":
    unittest.main()

