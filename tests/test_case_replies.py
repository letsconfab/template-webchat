"""State-machine tests for immutable Feedback Case correspondence."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.database import Base, get_db
from backend.models import diagnostics, invite, settings  # noqa: F401
from backend.models.chat import ChatSession
from backend.models.feedback_case import CaseReply, FeedbackCase
from backend.models.user import User
from backend.models.wiki import ChatMessage, UserFeedback
from backend.routers import admin_feedback_cases, feedback_cases
from backend.services.auth import create_access_token
from backend.services.redaction import project_text


class CaseReplyApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        database = Path(cls.tempdir.name) / "replies.db"
        cls.engine = create_async_engine(f"sqlite+aiosqlite:///{database}")

        @event.listens_for(cls.engine.sync_engine, "connect")
        def enable_foreign_keys(connection, _record) -> None:
            connection.execute("PRAGMA foreign_keys=ON")

        cls.sessions = async_sessionmaker(cls.engine, expire_on_commit=False)
        cls.case_id = asyncio.run(cls._seed())
        app = FastAPI()
        app.include_router(feedback_cases.router)
        app.include_router(admin_feedback_cases.router)

        async def override_db():
            async with cls.sessions() as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        cls.client = TestClient(app)

    @classmethod
    async def _seed(cls) -> str:
        async with cls.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with cls.sessions() as session:
            owner = User(
                id=301,
                email="owner@example.test",
                password_hash="hash",
                role="user",
                is_active=True,
            )
            other = User(
                id=302,
                email="other@example.test",
                password_hash="hash",
                role="user",
                is_active=True,
            )
            admin = User(
                id=303,
                email="admin@example.test",
                password_hash="hash",
                role="admin",
                is_active=True,
            )
            deletable_admin = User(
                id=304,
                email="former-admin@example.test",
                password_hash="hash",
                role="admin",
                is_active=True,
            )
            chat_session = ChatSession(
                client_uuid=str(uuid4()),
                user_id=owner.id,
                ownership_state="owned",
            )
            session.add_all([owner, other, admin, deletable_admin, chat_session])
            await session.flush()
            question = ChatMessage(
                chat_session_id=chat_session.id,
                session_id=chat_session.client_uuid,
                role="user",
                content="Question",
            )
            answer = ChatMessage(
                chat_session_id=chat_session.id,
                session_id=chat_session.client_uuid,
                role="assistant",
                content="Answer",
            )
            session.add_all([question, answer])
            await session.flush()
            feedback = UserFeedback(
                user_id=owner.id,
                feedback_type="thumbs_down",
                rating=1,
                message="Initial feedback",
                categories=["inaccurate"],
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
        asyncio.run(cls.engine.dispose())
        cls.tempdir.cleanup()

    @staticmethod
    def headers(user_id: int) -> dict[str, str]:
        return {
            "Authorization": "Bearer "
            + create_access_token({"sub": str(user_id)})
        }

    def test_state_transitions_resolution_and_reopening(self) -> None:
        user_reply = self.client.post(
            f"/api/feedback-cases/{self.case_id}/replies",
            json={"text": "I am Jane Doe in Boston."},
            headers=self.headers(301),
        )
        admin_reply = self.client.post(
            f"/api/admin/feedback-cases/{self.case_id}/replies",
            json={"text": "We are investigating."},
            headers=self.headers(303),
        )
        resolved = self.client.post(
            f"/api/admin/feedback-cases/{self.case_id}/resolve",
            headers=self.headers(303),
        )
        reopened_by_user = self.client.post(
            f"/api/feedback-cases/{self.case_id}/replies",
            json={"text": "One more detail."},
            headers=self.headers(301),
        )
        self.client.post(
            f"/api/admin/feedback-cases/{self.case_id}/resolve",
            headers=self.headers(303),
        )
        reopened_by_admin = self.client.post(
            f"/api/admin/feedback-cases/{self.case_id}/replies",
            json={"text": "A follow-up from admin."},
            headers=self.headers(303),
        )

        self.assertEqual(user_reply.json()["status"], "awaiting_admin")
        self.assertEqual(admin_reply.json()["status"], "awaiting_user")
        self.assertEqual(resolved.json()["status"], "resolved")
        self.assertEqual(reopened_by_user.json()["status"], "awaiting_admin")
        self.assertEqual(reopened_by_admin.json()["status"], "awaiting_user")

    def test_validation_authorization_isolation_and_immutability(self) -> None:
        empty = self.client.post(
            f"/api/feedback-cases/{self.case_id}/replies",
            json={"text": "   "},
            headers=self.headers(301),
        )
        too_long = self.client.post(
            f"/api/feedback-cases/{self.case_id}/replies",
            json={"text": "x" * 4001},
            headers=self.headers(301),
        )
        isolated = self.client.post(
            f"/api/feedback-cases/{self.case_id}/replies",
            json={"text": "Not mine"},
            headers=self.headers(302),
        )
        user_resolve = self.client.post(
            f"/api/admin/feedback-cases/{self.case_id}/resolve",
            headers=self.headers(301),
        )
        edit = self.client.put(
            f"/api/feedback-cases/{self.case_id}/replies/1",
            json={"text": "changed"},
            headers=self.headers(301),
        )
        delete = self.client.delete(
            f"/api/feedback-cases/{self.case_id}/replies/1",
            headers=self.headers(301),
        )

        self.assertEqual(empty.status_code, 422)
        self.assertEqual(too_long.status_code, 422)
        self.assertEqual(isolated.status_code, 404)
        self.assertEqual(user_resolve.status_code, 403)
        self.assertIn(edit.status_code, (404, 405))
        self.assertIn(delete.status_code, (404, 405))

    def test_owner_raw_and_admin_redacted_views_are_ordered(self) -> None:
        raw = "Contact Jane Doe in Boston at jane@example.com"
        self.client.post(
            f"/api/feedback-cases/{self.case_id}/replies",
            json={"text": raw},
            headers=self.headers(301),
        )
        self.client.post(
            f"/api/admin/feedback-cases/{self.case_id}/replies",
            json={"text": "Admin reply"},
            headers=self.headers(303),
        )

        owner = self.client.get(
            f"/api/feedback-cases/{self.case_id}",
            headers=self.headers(301),
        )
        admin = self.client.get(
            f"/api/admin/feedback-cases/{self.case_id}/replay",
            headers=self.headers(303),
        )

        owner_replies = owner.json()["replies"]
        admin_replies = admin.json()["replies"]
        self.assertEqual(owner_replies[-2]["text"], raw)
        self.assertEqual(owner_replies[-1]["text"], "Admin reply")
        self.assertNotIn("Jane Doe", admin_replies[-2]["text"])
        self.assertNotIn("jane@example.com", admin_replies[-2]["text"])
        self.assertEqual(admin_replies[-1]["text"], "Admin reply")
        self.assertEqual(
            [reply["id"] for reply in owner_replies],
            sorted(reply["id"] for reply in owner_replies),
        )

    def test_concurrent_replies_are_both_retained(self) -> None:
        def post_reply(index: int) -> int:
            response = self.client.post(
                f"/api/feedback-cases/{self.case_id}/replies",
                json={"text": f"Concurrent {index}"},
                headers=self.headers(301),
            )
            return response.status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(post_reply, range(2)))

        self.assertEqual(statuses, [201, 201])
        detail = self.client.get(
            f"/api/feedback-cases/{self.case_id}",
            headers=self.headers(301),
        )
        concurrent = [
            reply
            for reply in detail.json()["replies"]
            if reply["text"].startswith("Concurrent")
        ]
        self.assertEqual(len(concurrent), 2)

    def test_deleted_admin_keeps_role_snapshot_and_filters_work(self) -> None:
        created = self.client.post(
            f"/api/admin/feedback-cases/{self.case_id}/replies",
            json={"text": "Reply from a departing admin"},
            headers=self.headers(304),
        )
        reply_id = created.json()["id"]

        async def delete_admin_and_read_reply() -> tuple[int | None, str]:
            async with self.sessions() as session:
                admin = await session.get(User, 304)
                await session.delete(admin)
                await session.commit()
            async with self.sessions() as session:
                reply = await session.get(CaseReply, reply_id)
                return reply.author_id, reply.author_role

        self.assertEqual(
            asyncio.run(delete_admin_and_read_reply()),
            (None, "admin"),
        )

        filtered = self.client.get(
            "/api/admin/feedback-cases",
            params={
                "category": "inaccurate",
                "email": "o***",
            },
            headers=self.headers(303),
        )
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.json()["cases"][0]["case_id"], self.case_id)


if __name__ == "__main__":
    unittest.main()
