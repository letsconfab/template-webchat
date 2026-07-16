"""Tests for admin user management (PR 3)."""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta
from pathlib import Path
import tempfile

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.database import Base, get_db
from backend.models import invite as invite_models  # noqa: F401
from backend.models import settings as settings_models  # noqa: F401
from backend.models.chat import ChatSession  # noqa: F401
from backend.models.diagnostics import AdminProjection  # noqa: F401
from backend.models.feedback_case import FeedbackCase  # noqa: F401
from backend.models.invite import Invite, InviteStatus
from backend.models.user import User, UserRole
from backend.models.wiki import ChatMessage, UserFeedback  # noqa: F401
from backend.routers import auth as auth_router
from backend.routers import users as users_router
from backend.services.auth import create_access_token, get_password_hash


class AdminUsersApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        database = Path(cls.tempdir.name) / "admin_users.db"
        cls.engine = create_async_engine(f"sqlite+aiosqlite:///{database}")

        @event.listens_for(cls.engine.sync_engine, "connect")
        def enable_foreign_keys(connection, _record) -> None:
            connection.execute("PRAGMA foreign_keys=ON")

        cls.sessions = async_sessionmaker(cls.engine, expire_on_commit=False)
        asyncio.run(cls._create_schema())

        app = FastAPI()
        app.include_router(users_router.router)
        app.include_router(auth_router.router)

        async def override_db():
            async with cls.sessions() as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        cls.client = TestClient(app)
        cls.admin_token = create_access_token({"sub": "1"})
        cls.admin2_token = create_access_token({"sub": "2"})
        cls.user_token = create_access_token({"sub": "3"})

    @classmethod
    def tearDownClass(cls) -> None:
        asyncio.run(cls.engine.dispose())
        cls.tempdir.cleanup()

    @classmethod
    async def _create_schema(cls) -> None:
        async with cls.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with cls.sessions() as session:
            session.add_all(
                [
                    User(
                        id=1,
                        email="admin@example.com",
                        password_hash=get_password_hash("password123"),
                        role=UserRole.ADMIN,
                        is_active=True,
                    ),
                    User(
                        id=2,
                        email="admin2@example.com",
                        password_hash=get_password_hash("password123"),
                        role=UserRole.ADMIN,
                        is_active=True,
                    ),
                    User(
                        id=3,
                        email="user@example.com",
                        password_hash=get_password_hash("password123"),
                        role=UserRole.USER,
                        is_active=True,
                    ),
                    User(
                        id=4,
                        email="inactive@example.com",
                        password_hash=get_password_hash("password123"),
                        role=UserRole.USER,
                        is_active=False,
                    ),
                    User(
                        id=5,
                        email="stale@example.com",
                        password_hash=get_password_hash("password123"),
                        role=UserRole.USER,
                        is_active=True,
                        last_login_at=datetime.utcnow() - timedelta(days=120),
                    ),
                    User(
                        id=6,
                        email="unknown@example.com",
                        password_hash=get_password_hash("password123"),
                        role=UserRole.USER,
                        is_active=True,
                        last_login_at=None,
                        inferred_last_activity_at=None,
                    ),
                    User(
                        id=7,
                        email="recent@example.com",
                        password_hash=get_password_hash("password123"),
                        role=UserRole.USER,
                        is_active=True,
                        inferred_last_activity_at=datetime.utcnow() - timedelta(days=3),
                    ),
                ]
            )
            session.add(
                Invite(
                    email="stale@example.com",
                    token="pending-token-1",
                    role="user",
                    status=InviteStatus.PENDING,
                    expiry_date=datetime.utcnow() + timedelta(days=7),
                    created_by_id=1,
                )
            )
            await session.commit()

    def _auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def test_stats_route_reachable(self) -> None:
        response = self.client.get(
            "/api/admin/users/stats",
            headers=self._auth(self.admin_token),
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["total_users"], 7)
        self.assertEqual(body["active_users"], 6)
        # Active admins only; inactive users must not inflate regular_users.
        self.assertEqual(body["admin_users"], 2)
        self.assertEqual(body["regular_users"], 4)

    def test_self_deactivate_blocked(self) -> None:
        response = self.client.put(
            "/api/admin/users/1",
            headers=self._auth(self.admin_token),
            json={"is_active": False},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("deactivate yourself", response.json()["detail"])

    def test_email_update_does_not_trigger_self_deactivate_guard(self) -> None:
        response = self.client.put(
            "/api/admin/users/1",
            headers=self._auth(self.admin_token),
            json={"email": "admin-renamed@example.com"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        # Restore email for other tests
        self.client.put(
            "/api/admin/users/1",
            headers=self._auth(self.admin_token),
            json={"email": "admin@example.com"},
        )

    def test_last_admin_protection(self) -> None:
        # Demote admin2 first so only admin1 remains active.
        demote = self.client.put(
            "/api/admin/users/2",
            headers=self._auth(self.admin_token),
            json={"role": "user"},
        )
        self.assertEqual(demote.status_code, 200, demote.text)

        # Last admin demoting themselves is blocked by the last-admin guard.
        blocked = self.client.put(
            "/api/admin/users/1",
            headers=self._auth(self.admin_token),
            json={"role": "user"},
        )
        self.assertEqual(blocked.status_code, 400)
        self.assertIn("last active admin", blocked.json()["detail"])

        # Restore admin2 for remaining tests.
        restore = self.client.put(
            "/api/admin/users/2",
            headers=self._auth(self.admin_token),
            json={"role": "admin"},
        )
        self.assertEqual(restore.status_code, 200, restore.text)

    def test_self_demotion_blocked_when_other_admins_exist(self) -> None:
        response = self.client.put(
            "/api/admin/users/1",
            headers=self._auth(self.admin_token),
            json={"role": "user"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("demote yourself", response.json()["detail"])

    def test_sequential_last_admin_race_simulation(self) -> None:
        """Simulate two demotions in sequence after locking checks.

        SQLite drops FOR UPDATE, so true concurrent Postgres coverage is
        deferred; this sequential race still asserts the second demotion fails
        once only one active admin remains.
        """
        self.client.put(
            "/api/admin/users/2",
            headers=self._auth(self.admin_token),
            json={"role": "admin", "is_active": True},
        )

        first = self.client.put(
            "/api/admin/users/2",
            headers=self._auth(self.admin_token),
            json={"role": "user"},
        )
        self.assertEqual(first.status_code, 200, first.text)

        second = self.client.put(
            "/api/admin/users/1",
            headers=self._auth(self.admin_token),
            json={"role": "user"},
        )
        self.assertEqual(second.status_code, 400)
        self.assertIn("last active admin", second.json()["detail"])

        self.client.put(
            "/api/admin/users/2",
            headers=self._auth(self.admin_token),
            json={"is_active": True, "role": "admin"},
        )

    def test_pagination_envelope(self) -> None:
        response = self.client.get(
            "/api/admin/users",
            params={"skip": 0, "limit": 2, "sort_by": "email", "sort_order": "asc"},
            headers=self._auth(self.admin_token),
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertIn("items", body)
        self.assertEqual(body["skip"], 0)
        self.assertEqual(body["limit"], 2)
        self.assertEqual(body["total"], 7)
        self.assertEqual(len(body["items"]), 2)
        self.assertIn("is_admin", body["items"][0])
        self.assertIn("last_seen_at", body["items"][0])
        self.assertIn("last_seen_source", body["items"][0])

    def test_stale_and_unknown_semantics(self) -> None:
        stale = self.client.get(
            "/api/admin/users",
            params={"stale": True},
            headers=self._auth(self.admin_token),
        )
        self.assertEqual(stale.status_code, 200, stale.text)
        stale_emails = {u["email"] for u in stale.json()["items"]}
        self.assertIn("stale@example.com", stale_emails)
        self.assertNotIn("unknown@example.com", stale_emails)
        self.assertNotIn("recent@example.com", stale_emails)

        not_stale = self.client.get(
            "/api/admin/users",
            params={"stale": False},
            headers=self._auth(self.admin_token),
        )
        self.assertEqual(not_stale.status_code, 200, not_stale.text)
        not_stale_emails = {u["email"] for u in not_stale.json()["items"]}
        self.assertIn("unknown@example.com", not_stale_emails)
        self.assertIn("recent@example.com", not_stale_emails)
        self.assertNotIn("stale@example.com", not_stale_emails)

        unknown = next(
            u for u in not_stale.json()["items"] if u["email"] == "unknown@example.com"
        )
        self.assertIsNone(unknown["last_seen_at"])
        self.assertIsNone(unknown["last_seen_source"])

        recent = next(
            u for u in not_stale.json()["items"] if u["email"] == "recent@example.com"
        )
        self.assertEqual(recent["last_seen_source"], "inferred")

    def test_deactivate_cancels_pending_invites(self) -> None:
        response = self.client.put(
            "/api/admin/users/5",
            headers=self._auth(self.admin_token),
            json={"is_active": False},
        )
        self.assertEqual(response.status_code, 200, response.text)

        async def read_invite() -> str:
            async with self.sessions() as session:
                invite = (
                    await session.execute(
                        select(Invite).where(Invite.email == "stale@example.com")
                    )
                ).scalar_one()
                return invite.status

        status_value = asyncio.run(read_invite())
        self.assertEqual(status_value, InviteStatus.CANCELLED)

        # Reactivate for other tests.
        self.client.put(
            "/api/admin/users/5",
            headers=self._auth(self.admin_token),
            json={"is_active": True},
        )

    def test_last_login_at_written_on_login(self) -> None:
        before = datetime.utcnow() - timedelta(seconds=1)
        response = self.client.post(
            "/api/auth/login",
            json={"email": "user@example.com", "password": "password123"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("access_token", response.json())

        async def read_login() -> datetime | None:
            async with self.sessions() as session:
                user = (
                    await session.execute(select(User).where(User.id == 3))
                ).scalar_one()
                return user.last_login_at

        last_login = asyncio.run(read_login())
        self.assertIsNotNone(last_login)
        assert last_login is not None
        self.assertGreaterEqual(last_login, before)


if __name__ == "__main__":
    unittest.main()
