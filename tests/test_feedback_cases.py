"""API tests for tester-visible Feedback Cases."""

from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.database import Base, get_db
from backend.models import invite, settings  # noqa: F401
from backend.models.chat import ChatSession
from backend.models.feedback_case import FeedbackCase
from backend.models.user import User
from backend.models.wiki import ChatMessage, UserFeedback
from backend.routers import feedback, feedback_cases, users
from backend.services.auth import create_access_token


class FeedbackCaseApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        database = Path(cls.tempdir.name) / "cases.db"
        cls.engine = create_async_engine(f"sqlite+aiosqlite:///{database}")

        @event.listens_for(cls.engine.sync_engine, "connect")
        def enable_foreign_keys(connection, _record) -> None:
            connection.execute("PRAGMA foreign_keys=ON")

        cls.sessions = async_sessionmaker(cls.engine, expire_on_commit=False)
        asyncio.run(cls._create_schema())
        app = FastAPI()
        app.include_router(feedback.router)
        app.include_router(feedback_cases.router)
        app.include_router(users.router)

        async def override_db():
            async with cls.sessions() as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        cls.client = TestClient(app)

    @classmethod
    async def _create_schema(cls) -> None:
        async with cls.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with cls.sessions() as session:
            session.add_all(
                [
                    User(
                        id=101,
                        email="tester@example.test",
                        password_hash="hash",
                        role="user",
                        is_active=True,
                    ),
                    User(
                        id=102,
                        email="other@example.test",
                        password_hash="hash",
                        role="user",
                        is_active=True,
                    ),
                    User(
                        id=103,
                        email="admin@example.test",
                        password_hash="hash",
                        role="admin",
                        is_active=True,
                    ),
                ]
            )
            owner_session = ChatSession(
                client_uuid=str(uuid4()),
                user_id=101,
                ownership_state="owned",
            )
            other_session = ChatSession(
                client_uuid=str(uuid4()),
                user_id=102,
                ownership_state="owned",
            )
            session.add_all([owner_session, other_session])
            await session.flush()
            session.add_all(
                [
                    ChatMessage(
                        id=1001,
                        chat_session_id=owner_session.id,
                        session_id=owner_session.client_uuid,
                        role="user",
                        content="Owner question",
                    ),
                    ChatMessage(
                        id=1002,
                        chat_session_id=owner_session.id,
                        session_id=owner_session.client_uuid,
                        role="assistant",
                        content="Owner answer",
                    ),
                    ChatMessage(
                        id=2001,
                        chat_session_id=other_session.id,
                        session_id=other_session.client_uuid,
                        role="assistant",
                        content="Other answer",
                    ),
                ]
            )
            await session.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        asyncio.run(cls.engine.dispose())
        cls.tempdir.cleanup()

    def setUp(self) -> None:
        async def reset_feedback() -> None:
            async with self.sessions() as session:
                await session.execute(delete(FeedbackCase))
                await session.execute(delete(UserFeedback))
                await session.commit()

        asyncio.run(reset_feedback())

    @staticmethod
    def headers(user_id: int = 101) -> dict[str, str]:
        token = create_access_token({"sub": str(user_id)})
        return {"Authorization": f"Bearer {token}"}

    def test_positive_stays_analytics_and_negative_creates_case(self) -> None:
        positive = self.client.post(
            "/api/feedback",
            json={
                "feedback_type": "thumbs_up",
                "rating": 5,
                "chat_message_id": 1002,
            },
            headers=self.headers(),
        )
        negative = self.client.post(
            "/api/feedback",
            json={
                "feedback_type": "thumbs_down",
                "rating": 1,
                "chat_message_id": 1002,
                "categories": ["inaccurate"],
                "message": "This answer is wrong.",
            },
            headers=self.headers(),
        )

        self.assertEqual(positive.status_code, 201)
        self.assertNotIn("case_id", positive.json())
        self.assertEqual(negative.status_code, 201)
        self.assertIsInstance(negative.json()["case_id"], str)

        async def cases() -> list[FeedbackCase]:
            async with self.sessions() as session:
                result = await session.execute(select(FeedbackCase))
                return list(result.scalars())

        persisted = asyncio.run(cases())
        self.assertEqual(len(persisted), 1)
        self.assertEqual(persisted[0].status, "awaiting_admin")

    def test_retry_and_revote_do_not_duplicate_cases(self) -> None:
        payload = {
            "feedback_type": "thumbs_down",
            "rating": 1,
            "chat_message_id": 1002,
        }
        first = self.client.post(
            "/api/feedback", json=payload, headers=self.headers()
        )
        retry = self.client.post(
            "/api/feedback", json=payload, headers=self.headers()
        )
        positive_revote = self.client.post(
            "/api/feedback",
            json={
                "feedback_type": "thumbs_up",
                "rating": 5,
                "chat_message_id": 1002,
            },
            headers=self.headers(),
        )

        self.assertEqual(first.json()["case_id"], retry.json()["case_id"])
        self.assertNotIn("case_id", positive_revote.json())

        async def counts() -> tuple[int, int]:
            async with self.sessions() as session:
                feedback_rows = await session.execute(select(UserFeedback))
                case_rows = await session.execute(select(FeedbackCase))
                return (
                    len(feedback_rows.scalars().all()),
                    len(case_rows.scalars().all()),
                )

        self.assertEqual(asyncio.run(counts()), (1, 1))

    def test_arbitrary_and_cross_user_message_ids_are_rejected(self) -> None:
        missing = self.client.post(
            "/api/feedback",
            json={
                "feedback_type": "thumbs_down",
                "rating": 1,
                "chat_message_id": 999999,
            },
            headers=self.headers(),
        )
        other = self.client.post(
            "/api/feedback",
            json={
                "feedback_type": "thumbs_down",
                "rating": 1,
                "chat_message_id": 2001,
            },
            headers=self.headers(),
        )

        self.assertEqual(missing.status_code, 404)
        self.assertEqual(other.status_code, 404)

    async def _add_owner_exchange(self, base_id: int) -> int:
        async with self.sessions() as session:
            result = await session.execute(
                select(ChatSession).where(ChatSession.user_id == 101)
            )
            chat_session = result.scalar_one()
            session.add_all(
                [
                    ChatMessage(
                        id=base_id,
                        chat_session_id=chat_session.id,
                        session_id=chat_session.client_uuid,
                        role="user",
                        content=f"Question {base_id}",
                    ),
                    ChatMessage(
                        id=base_id + 1,
                        chat_session_id=chat_session.id,
                        session_id=chat_session.client_uuid,
                        role="assistant",
                        content=f"Answer {base_id + 1}",
                    ),
                ]
            )
            await session.commit()
        return base_id + 1

    def test_owner_list_detail_pagination_and_case_isolation(self) -> None:
        message_ids = [
            1002,
            asyncio.run(self._add_owner_exchange(3000)),
            asyncio.run(self._add_owner_exchange(4000)),
        ]
        case_ids = []
        for message_id in message_ids:
            response = self.client.post(
                "/api/feedback",
                json={
                    "feedback_type": "thumbs_down",
                    "rating": 1,
                    "chat_message_id": message_id,
                    "categories": ["incomplete"],
                    "message": f"Problem with {message_id}",
                },
                headers=self.headers(),
            )
            case_ids.append(response.json()["case_id"])

        first_page = self.client.get(
            "/api/feedback-cases",
            params={"limit": 2},
            headers=self.headers(),
        )
        second_page = self.client.get(
            "/api/feedback-cases",
            params={
                "limit": 2,
                "cursor": first_page.json()["next_cursor"],
            },
            headers=self.headers(),
        )
        detail = self.client.get(
            f"/api/feedback-cases/{case_ids[1]}",
            headers=self.headers(),
        )
        isolated = self.client.get(
            f"/api/feedback-cases/{case_ids[1]}",
            headers=self.headers(102),
        )

        self.assertEqual(len(first_page.json()["cases"]), 2)
        self.assertEqual(len(second_page.json()["cases"]), 1)
        self.assertIsNone(second_page.json()["next_cursor"])
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["status"], "awaiting_admin")
        self.assertEqual(detail.json()["categories"], ["incomplete"])
        self.assertIn("Question", detail.json()["rated_exchange"]["user"]["content"])
        self.assertIn(
            "Answer",
            detail.json()["rated_exchange"]["assistant"]["content"],
        )
        self.assertEqual(isolated.status_code, 404)

    def test_account_deletion_cascades_cases_without_deleting_admin(self) -> None:
        async def seed_deletable_user() -> int:
            async with self.sessions() as session:
                user = User(
                    id=104,
                    email="delete@example.test",
                    password_hash="hash",
                    role="user",
                    is_active=True,
                )
                chat_session = ChatSession(
                    client_uuid=str(uuid4()),
                    user_id=104,
                    ownership_state="owned",
                )
                session.add_all([user, chat_session])
                await session.flush()
                message = ChatMessage(
                    id=5001,
                    chat_session_id=chat_session.id,
                    session_id=chat_session.client_uuid,
                    role="assistant",
                    content="Delete me",
                )
                session.add(message)
                await session.commit()
                return message.id

        message_id = asyncio.run(seed_deletable_user())
        created = self.client.post(
            "/api/feedback",
            json={
                "feedback_type": "thumbs_down",
                "rating": 1,
                "chat_message_id": message_id,
            },
            headers=self.headers(104),
        )
        self.assertEqual(created.status_code, 201)

        deleted = self.client.delete(
            "/api/admin/users/104",
            headers=self.headers(103),
        )
        self.assertEqual(deleted.status_code, 200)

        async def remaining() -> tuple[int, bool]:
            async with self.sessions() as session:
                cases = await session.execute(
                    select(FeedbackCase).where(FeedbackCase.user_id == 104)
                )
                admin = await session.get(User, 103)
                return len(cases.scalars().all()), admin is not None

        self.assertEqual(asyncio.run(remaining()), (0, True))


if __name__ == "__main__":
    unittest.main()
