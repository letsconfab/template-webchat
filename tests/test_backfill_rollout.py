"""Legacy backfill and phased-rollout behavior."""

from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.database import Base, get_db
from backend.models import diagnostics, invite  # noqa: F401
from backend.models.chat import ChatSession
from backend.models.diagnostics import AdminProjection, ExecutionTrace
from backend.models.feedback_case import FeedbackCase
from backend.models.settings import SystemSettings
from backend.models.user import User
from backend.models.wiki import ChatMessage, UserFeedback
from backend.routers import (
    admin_feedback_cases,
    case_notifications,
    feedback_cases,
    settings,
    users,
)
from backend.services.auth import create_access_token
from backend.services.feedback_backfill import run_feedback_backfill
from backend.services.redaction import redactor


class BackfillRolloutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        database = Path(cls.tempdir.name) / "backfill.db"
        cls.engine = create_async_engine(f"sqlite+aiosqlite:///{database}")

        @event.listens_for(cls.engine.sync_engine, "connect")
        def enable_foreign_keys(connection, _record) -> None:
            connection.execute("PRAGMA foreign_keys=ON")

        cls.sessions = async_sessionmaker(cls.engine, expire_on_commit=False)
        asyncio.run(cls._seed())
        app = FastAPI()
        app.include_router(settings.router)
        app.include_router(feedback_cases.router)
        app.include_router(admin_feedback_cases.router)
        app.include_router(case_notifications.router)
        app.include_router(users.router)

        async def override_db():
            async with cls.sessions() as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        cls.client = TestClient(app)

    @classmethod
    async def _seed(cls) -> None:
        async with cls.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with cls.sessions() as session:
            owner = User(
                id=501,
                email="owner@example.test",
                password_hash="hash",
                role="user",
                is_active=True,
            )
            conflicting = User(
                id=502,
                email="conflict@example.test",
                password_hash="hash",
                role="user",
                is_active=True,
            )
            admin = User(
                id=503,
                email="admin@example.test",
                password_hash="hash",
                role="admin",
                is_active=True,
            )
            system_settings = SystemSettings(
                is_configured=True,
                app_name="Rollout Test",
                use_tls=True,
                session_timeout_minutes=30,
                max_login_attempts=5,
                email_notifications_enabled=True,
                user_registration_enabled=True,
                admin_replay_enabled=False,
                tester_correspondence_enabled=False,
                tester_email_notifications_enabled=False,
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
            session.add_all([owner, conflicting, admin, system_settings])
            await session.flush()
            messages = [
                ChatMessage(
                    id=5101,
                    session_id="legacy-owned",
                    role="user",
                    content="Owned question from Jane Doe",
                ),
                ChatMessage(
                    id=5102,
                    session_id="legacy-owned",
                    role="assistant",
                    content="Owned answer echoes Jane Doe",
                ),
                ChatMessage(
                    id=5201,
                    session_id="legacy-conflict",
                    role="assistant",
                    content="Conflicting answer one",
                ),
                ChatMessage(
                    id=5202,
                    session_id="legacy-conflict",
                    role="assistant",
                    content="Conflicting answer two",
                ),
                ChatMessage(
                    id=5301,
                    session_id="legacy-ownerless",
                    role="assistant",
                    content="Ownerless answer",
                ),
            ]
            session.add_all(messages)
            await session.flush()
            session.add_all(
                [
                    UserFeedback(
                        user_id=501,
                        feedback_type="thumbs_down",
                        rating=1,
                        message="Owned negative",
                        chat_message_id=5102,
                    ),
                    UserFeedback(
                        user_id=501,
                        feedback_type="thumbs_up",
                        rating=5,
                        chat_message_id=5101,
                    ),
                    UserFeedback(
                        user_id=501,
                        feedback_type="thumbs_down",
                        rating=1,
                        chat_message_id=5201,
                    ),
                    UserFeedback(
                        user_id=502,
                        feedback_type="thumbs_down",
                        rating=1,
                        chat_message_id=5202,
                    ),
                ]
            )
            await session.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        asyncio.run(cls.engine.dispose())
        cls.tempdir.cleanup()

    @staticmethod
    def headers(user_id: int) -> dict[str, str]:
        return {
            "Authorization": "Bearer "
            + create_access_token({"sub": str(user_id)})
        }

    def test_resumable_backfill_conservative_ownership_and_rollout_flags(self) -> None:
        blocked = self.client.put(
            "/api/settings/current",
            json={"admin_replay_enabled": True},
            headers=self.headers(503),
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(
            self.client.get(
                "/api/admin/feedback-cases",
                headers=self.headers(503),
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                "/api/feedback-cases",
                headers=self.headers(501),
            ).status_code,
            404,
        )

        original = redactor.redact
        redactor.redact = Mock(side_effect=RuntimeError("temporary model failure"))
        try:
            failed_run = asyncio.run(run_feedback_backfill(self.sessions))
        finally:
            redactor.redact = original
        self.assertGreater(failed_run["failed"], 0)
        self.assertEqual(failed_run["quarantined"], 2)

        resumed = asyncio.run(run_feedback_backfill(self.sessions))
        repeated = asyncio.run(run_feedback_backfill(self.sessions))
        self.assertEqual(resumed["pending"], 0)
        self.assertEqual(repeated["pending"], 0)

        async def inspect_backfill():
            async with self.sessions() as session:
                chat_sessions = list(
                    (await session.execute(select(ChatSession))).scalars()
                )
                cases = list(
                    (await session.execute(select(FeedbackCase))).scalars()
                )
                traces = (
                    await session.execute(select(func.count(ExecutionTrace.id)))
                ).scalar()
                failed_projections = (
                    await session.execute(
                        select(func.count(AdminProjection.id)).where(
                            AdminProjection.status == "failed"
                        )
                    )
                ).scalar()
                return chat_sessions, cases, traces, failed_projections

        chat_sessions, cases, traces, failed_projections = asyncio.run(
            inspect_backfill()
        )
        self.assertEqual(
            sorted(session.ownership_state for session in chat_sessions),
            ["owned", "quarantined", "quarantined"],
        )
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0].user_id, 501)
        self.assertEqual(traces, 0)
        self.assertEqual(failed_projections, 0)

        readiness = self.client.get(
            "/api/admin/feedback-cases/rollout/readiness",
            headers=self.headers(503),
        )
        self.assertTrue(readiness.json()["ready"])
        self.assertEqual(readiness.json()["pending"], 0)

        admin_enabled = self.client.put(
            "/api/settings/current",
            json={"admin_replay_enabled": True},
            headers=self.headers(503),
        )
        self.assertEqual(admin_enabled.status_code, 200)
        self.assertEqual(
            len(
                self.client.get(
                    "/api/admin/feedback-cases",
                    headers=self.headers(503),
                ).json()["cases"]
            ),
            1,
        )
        self.assertEqual(
            self.client.get(
                "/api/feedback-cases",
                headers=self.headers(501),
            ).status_code,
            404,
        )
        admin_reply = self.client.post(
            f"/api/admin/feedback-cases/{cases[0].public_id}/replies",
            json={"text": "This must remain gated"},
            headers=self.headers(503),
        )
        admin_resolve = self.client.post(
            f"/api/admin/feedback-cases/{cases[0].public_id}/resolve",
            headers=self.headers(503),
        )
        self.assertEqual(
            (admin_reply.status_code, admin_reply.json()["detail"]),
            (404, "Feature not enabled"),
        )
        self.assertEqual(
            (admin_resolve.status_code, admin_resolve.json()["detail"]),
            (404, "Feature not enabled"),
        )

        correspondence_enabled = self.client.put(
            "/api/settings/current",
            json={"tester_correspondence_enabled": True},
            headers=self.headers(503),
        )
        self.assertEqual(correspondence_enabled.status_code, 200)
        owner_cases = self.client.get(
            "/api/feedback-cases",
            headers=self.headers(501),
        )
        self.assertEqual(len(owner_cases.json()["cases"]), 1)

        features = self.client.get(
            "/api/settings/features",
            headers=self.headers(501),
        ).json()
        self.assertTrue(features["admin_replay_enabled"])
        self.assertTrue(features["tester_correspondence_enabled"])
        self.assertFalse(features["tester_email_notifications_enabled"])

        email_enabled = self.client.put(
            "/api/settings/current",
            json={"tester_email_notifications_enabled": True},
            headers=self.headers(503),
        )
        self.assertEqual(email_enabled.status_code, 200)
        self.assertTrue(
            self.client.get(
                "/api/settings/features",
                headers=self.headers(501),
            ).json()["tester_email_notifications_enabled"]
        )

        rolled_back = self.client.put(
            "/api/settings/current",
            json={
                "admin_replay_enabled": False,
                "tester_correspondence_enabled": False,
                "tester_email_notifications_enabled": False,
            },
            headers=self.headers(503),
        )
        self.assertEqual(rolled_back.status_code, 200)
        self.assertEqual(
            self.client.get(
                "/api/admin/feedback-cases",
                headers=self.headers(503),
            ).status_code,
            404,
        )

        deleted = self.client.delete(
            "/api/admin/users/501",
            headers=self.headers(503),
        )
        self.assertEqual(deleted.status_code, 200)

        async def deletion_result() -> tuple[int, bool]:
            async with self.sessions() as session:
                case_count = (
                    await session.execute(select(func.count(FeedbackCase.id)))
                ).scalar()
                admin = await session.get(User, 503)
                return case_count, admin is not None

        self.assertEqual(asyncio.run(deletion_result()), (0, True))


if __name__ == "__main__":
    unittest.main()
