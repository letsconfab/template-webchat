"""Integration tests for authenticated Chat Session boundaries."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.websockets import WebSocketDisconnect

from backend.database import Base, get_db
from backend.models.chat import ChatSession
from backend.models.settings import SystemSettings
from backend.models.user import User
from backend.models.wiki import ChatMessage
from backend.services.auth import create_access_token
import backend.main as main


class DummyProvider:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def get_llm(self) -> object:
        return object()


class ChatSessionIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        database = Path(cls.tempdir.name) / "chat.db"
        cls.engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
        cls.sessions = async_sessionmaker(cls.engine, expire_on_commit=False)
        asyncio.run(cls._create_schema())

        main.AsyncSessionLocal = cls.sessions
        main.LLMProvider = DummyProvider
        main._settings_status_message = AsyncMock(return_value="ready")

        async def override_db():
            async with cls.sessions() as session:
                yield session

        main.app.dependency_overrides[get_db] = override_db
        cls.client = TestClient(main.app)

    @classmethod
    async def _create_schema(cls) -> None:
        async with cls.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with cls.sessions() as session:
            session.add(
                SystemSettings(
                    is_configured=True,
                    use_tls=True,
                    session_timeout_minutes=30,
                    max_login_attempts=5,
                    email_notifications_enabled=True,
                    user_registration_enabled=True,
                    llm_provider="openai",
                    llm_model="gpt-4o-mini",
                    rag_provider="openai",
                    rag_model="gpt-4o-mini",
                    google_drive_enabled=False,
                    neo4j_url="bolt://localhost:7687",
                    neo4j_user="neo4j",
                    neo4j_database="neo4j",
                    cocoindex_embedding_model="test",
                    graphrag_enabled=False,
                )
            )
            session.add(
                User(
                    id=1,
                    email="owner@example.test",
                    password_hash="hash",
                    role="user",
                    is_active=True,
                )
            )
            session.add(
                User(
                    id=2,
                    email="other@example.test",
                    password_hash="hash",
                    role="user",
                    is_active=True,
                )
            )
            session.add(
                User(
                    id=3,
                    email="inactive@example.test",
                    password_hash="hash",
                    role="user",
                    is_active=False,
                )
            )
            await session.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        main.app.dependency_overrides.clear()
        asyncio.run(cls.engine.dispose())
        cls.tempdir.cleanup()

    def token(self, user_id: int = 1, expires: timedelta | None = None) -> str:
        return create_access_token({"sub": str(user_id)}, expires_delta=expires)

    def test_valid_initial_auth_frame_binds_session(self) -> None:
        session_id = str(uuid4())

        with self.client.websocket_connect("/ws/chat") as websocket:
            websocket.send_json(
                {
                    "type": "auth",
                    "token": self.token(),
                    "session_id": session_id,
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                }
            )

            frame = websocket.receive_json()

        self.assertEqual(frame, {"type": "history", "messages": []})

    def assert_auth_close(self, payload: dict, expected_code: int) -> None:
        with self.client.websocket_connect("/ws/chat") as websocket:
            websocket.send_json(payload)
            with self.assertRaises(WebSocketDisconnect) as raised:
                websocket.receive_json()
        self.assertEqual(raised.exception.code, expected_code)

    def test_missing_invalid_and_expired_tokens_close_with_4401(self) -> None:
        session_id = str(uuid4())
        base = {"type": "auth", "session_id": session_id}

        self.assert_auth_close(base, 4401)
        self.assert_auth_close({**base, "token": "not-a-jwt"}, 4401)
        self.assert_auth_close(
            {
                **base,
                "token": self.token(expires=timedelta(seconds=-1)),
            },
            4401,
        )

    def test_inactive_user_closes_with_4403(self) -> None:
        self.assert_auth_close(
            {
                "type": "auth",
                "session_id": str(uuid4()),
                "token": self.token(user_id=3),
            },
            4403,
        )

    def test_cross_user_session_collision_is_non_disclosing(self) -> None:
        session_id = str(uuid4())
        with self.client.websocket_connect("/ws/chat") as websocket:
            websocket.send_json(
                {
                    "type": "auth",
                    "session_id": session_id,
                    "token": self.token(user_id=1),
                }
            )
            self.assertEqual(websocket.receive_json()["type"], "history")

        self.assert_auth_close(
            {
                "type": "auth",
                "session_id": session_id,
                "token": self.token(user_id=2),
            },
            4403,
        )

    async def _add_history(self, session_id: str) -> None:
        async with self.sessions() as session:
            result = await session.execute(
                select(ChatSession).where(ChatSession.client_uuid == session_id)
            )
            chat_session = result.scalar_one()
            session.add_all(
                [
                    ChatMessage(
                        chat_session_id=chat_session.id,
                        session_id=session_id,
                        role="user",
                        content="Earlier question",
                    ),
                    ChatMessage(
                        chat_session_id=chat_session.id,
                        session_id=session_id,
                        role="assistant",
                        content="Earlier answer",
                    ),
                ]
            )
            await session.commit()

    def test_owner_reconnect_receives_chronological_persisted_history(self) -> None:
        session_id = str(uuid4())
        auth = {
            "type": "auth",
            "session_id": session_id,
            "token": self.token(),
        }
        with self.client.websocket_connect("/ws/chat") as websocket:
            websocket.send_json(auth)
            websocket.receive_json()
        asyncio.run(self._add_history(session_id))

        with self.client.websocket_connect("/ws/chat") as websocket:
            websocket.send_json(auth)
            frame = websocket.receive_json()

        self.assertEqual(
            [(message["role"], message["content"]) for message in frame["messages"]],
            [
                ("user", "Earlier question"),
                ("assistant", "Earlier answer"),
            ],
        )

    def test_http_history_is_authenticated_and_owner_scoped(self) -> None:
        session_id = str(uuid4())
        auth = {
            "type": "auth",
            "session_id": session_id,
            "token": self.token(),
        }
        with self.client.websocket_connect("/ws/chat") as websocket:
            websocket.send_json(auth)
            websocket.receive_json()
        asyncio.run(self._add_history(session_id))

        owner = self.client.get(
            "/api/chat-history",
            params={"session_id": session_id},
            headers={"Authorization": f"Bearer {self.token()}"},
        )
        other = self.client.get(
            "/api/chat-history",
            params={"session_id": session_id},
            headers={"Authorization": f"Bearer {self.token(user_id=2)}"},
        )
        anonymous = self.client.get(
            "/api/chat-history",
            params={"session_id": session_id},
        )

        self.assertEqual(owner.status_code, 200)
        self.assertEqual(len(owner.json()["messages"]), 2)
        self.assertEqual(other.status_code, 404)
        self.assertEqual(anonymous.status_code, 401)

        cleared = self.client.delete(
            "/api/chat-history",
            params={"session_id": session_id},
            headers={"Authorization": f"Bearer {self.token()}"},
        )
        after = self.client.get(
            "/api/chat-history",
            params={"session_id": session_id},
            headers={"Authorization": f"Bearer {self.token()}"},
        )
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(after.json()["messages"], [])

    def test_concurrent_first_use_attempts_bind_once_to_the_same_owner(self) -> None:
        session_id = str(uuid4())
        payload = {
            "type": "auth",
            "session_id": session_id,
            "token": self.token(),
        }

        def connect() -> str:
            with self.client.websocket_connect("/ws/chat") as websocket:
                websocket.send_json(payload)
                return websocket.receive_json()["type"]

        with ThreadPoolExecutor(max_workers=2) as executor:
            frame_types = list(executor.map(lambda _: connect(), range(2)))

        self.assertEqual(frame_types, ["history", "history"])

        async def count() -> int:
            async with self.sessions() as session:
                result = await session.execute(
                    select(ChatSession).where(
                        ChatSession.client_uuid == session_id
                    )
                )
                return len(result.scalars().all())

        self.assertEqual(asyncio.run(count()), 1)

    def test_new_messages_reference_the_authenticated_chat_session(self) -> None:
        session_id = str(uuid4())
        with self.client.websocket_connect("/ws/chat") as websocket:
            websocket.send_json(
                {
                    "type": "auth",
                    "session_id": session_id,
                    "token": self.token(),
                }
            )
            websocket.receive_json()
            websocket.receive_json()
            websocket.send_json({"message": "New question"})
            while websocket.receive_json()["type"] != "end":
                pass

        async def persisted_messages() -> tuple[int, list[ChatMessage]]:
            async with self.sessions() as session:
                result = await session.execute(
                    select(ChatSession).where(
                        ChatSession.client_uuid == session_id
                    )
                )
                chat_session = result.scalar_one()
                messages = await session.execute(
                    select(ChatMessage)
                    .where(ChatMessage.chat_session_id == chat_session.id)
                    .order_by(ChatMessage.id)
                )
                return chat_session.id, list(messages.scalars())

        chat_session_id, messages = asyncio.run(persisted_messages())
        self.assertEqual([message.role for message in messages], ["user", "assistant"])
        self.assertTrue(
            all(message.chat_session_id == chat_session_id for message in messages)
        )


if __name__ == "__main__":
    unittest.main()
