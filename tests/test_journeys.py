"""Unit / integration tests for administrator-curated starter journeys."""

from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.database import Base, get_db
from backend.models.settings import SystemSettings
from backend.models.user import User
from backend.services.auth import create_access_token
import backend.main as main


class JourneyApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        database = Path(cls.tempdir.name) / "journeys.db"
        cls.engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
        cls.sessions = async_sessionmaker(cls.engine, expire_on_commit=False)
        asyncio.run(cls._create_schema())

        main.AsyncSessionLocal = cls.sessions

        async def override_db():
            async with cls.sessions() as session:
                yield session

        main.app.dependency_overrides[get_db] = override_db
        cls.client = TestClient(main.app)
        cls.admin_token = create_access_token({"sub": "1"})
        cls.user_token = create_access_token({"sub": "2"})

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
                    email="admin@example.test",
                    password_hash="hash",
                    role="admin",
                    is_active=True,
                )
            )
            session.add(
                User(
                    id=2,
                    email="tester@example.test",
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

    def test_admin_creates_journey_and_tester_sees_only_active(self) -> None:
        create = self.client.post(
            "/api/admin/journeys",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={
                "title": "Licensing basics",
                "purpose": "Understand ALO licensing boundaries",
                "starter_prompt": "What does ALO say about licensing?",
                "icon": "book",
                "display_order": 1,
                "is_active": True,
                "knowledge_source_labels": ["ALO Licensing Policy"],
            },
        )
        self.assertEqual(create.status_code, 201, create.text)
        journey_id = create.json()["id"]

        inactive = self.client.post(
            "/api/admin/journeys",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={
                "title": "Hidden",
                "purpose": "Should not show",
                "starter_prompt": "hidden",
                "display_order": 2,
                "is_active": False,
                "knowledge_source_labels": [],
            },
        )
        self.assertEqual(inactive.status_code, 201)

        public = self.client.get(
            "/api/journeys",
            headers={"Authorization": f"Bearer {self.user_token}"},
        )
        self.assertEqual(public.status_code, 200)
        titles = [j["title"] for j in public.json()]
        self.assertEqual(titles, ["Licensing basics"])
        self.assertEqual(public.json()[0]["starter_prompt"], "What does ALO say about licensing?")

        # Tester cannot create journeys
        denied = self.client.post(
            "/api/admin/journeys",
            headers={"Authorization": f"Bearer {self.user_token}"},
            json={
                "title": "Nope",
                "purpose": "x",
                "starter_prompt": "x",
                "display_order": 3,
                "is_active": True,
            },
        )
        self.assertIn(denied.status_code, (401, 403))

        deleted = self.client.delete(
            f"/api/admin/journeys/{journey_id}",
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(deleted.status_code, 204)


if __name__ == "__main__":
    unittest.main()
