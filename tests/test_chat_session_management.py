"""Unit / integration tests for Chat Session management API."""

from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.database import Base, get_db
from backend.models.chat import ChatSession
from backend.models.settings import SystemSettings
from backend.models.user import User
from backend.models.wiki import ChatMessage
from backend.services.auth import create_access_token
import backend.main as main


class ChatSessionManagementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        database = Path(cls.tempdir.name) / "sessions.db"
        cls.engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
        cls.sessions = async_sessionmaker(cls.engine, expire_on_commit=False)
        asyncio.run(cls._create_schema())

        main.AsyncSessionLocal = cls.sessions

        async def override_db():
            async with cls.sessions() as session:
                yield session

        main.app.dependency_overrides[get_db] = override_db
        cls.client = TestClient(main.app)
        cls.token = create_access_token({"sub": "1"})
        cls.other_token = create_access_token({"sub": "2"})

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
            await session.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        main.app.dependency_overrides.clear()
        asyncio.run(cls.engine.dispose())
        cls.tempdir.cleanup()

    def _auth(self, token: str | None = None) -> dict:
        return {"Authorization": f"Bearer {token or self.token}"}

    def test_create_list_rename_and_delete_owned_session(self) -> None:
        create = self.client.post("/api/chat-sessions", headers=self._auth())
        self.assertEqual(create.status_code, 201, create.text)
        body = create.json()
        self.assertIn("client_uuid", body)
        self.assertEqual(body["title"], "New chat")

        listed = self.client.get("/api/chat-sessions", headers=self._auth())
        self.assertEqual(listed.status_code, 200)
        self.assertTrue(any(s["client_uuid"] == body["client_uuid"] for s in listed.json()))

        renamed = self.client.patch(
            f"/api/chat-sessions/{body['client_uuid']}",
            headers=self._auth(),
            json={"title": "Facilitation journey"},
        )
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json()["title"], "Facilitation journey")

        deleted = self.client.delete(
            f"/api/chat-sessions/{body['client_uuid']}",
            headers=self._auth(),
        )
        self.assertEqual(deleted.status_code, 204)

        listed_after = self.client.get("/api/chat-sessions", headers=self._auth())
        self.assertFalse(
            any(s["client_uuid"] == body["client_uuid"] for s in listed_after.json())
        )

    def test_cannot_access_another_users_session(self) -> None:
        create = self.client.post("/api/chat-sessions", headers=self._auth())
        uuid = create.json()["client_uuid"]

        forbidden = self.client.get(
            f"/api/chat-sessions/{uuid}",
            headers=self._auth(self.other_token),
        )
        self.assertEqual(forbidden.status_code, 404)

        forbidden_del = self.client.delete(
            f"/api/chat-sessions/{uuid}",
            headers=self._auth(self.other_token),
        )
        self.assertEqual(forbidden_del.status_code, 404)


if __name__ == "__main__":
    unittest.main()
