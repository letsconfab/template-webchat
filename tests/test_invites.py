"""Tests for invite integrity (PR 4)."""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta
from pathlib import Path
import tempfile

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
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
from backend.routers import invites as invites_router
from backend.schemas.invite import InviteCreate
from backend.services.auth import create_access_token, get_password_hash
from backend.services.invites import (
    InviteClaimError,
    canonicalize_email,
    claim_invite,
    reap_expired_invites,
)


class CanonicalEmailUnitTests(unittest.TestCase):
    def test_canonicalize_trims_and_lowercases(self) -> None:
        self.assertEqual(canonicalize_email("  Admin@Example.COM "), "admin@example.com")


class InviteCreateRoleTests(unittest.TestCase):
    def test_role_enum_rejects_invalid(self) -> None:
        with self.assertRaises(ValidationError):
            InviteCreate(email="a@example.com", role="wizard")

    def test_role_enum_accepts_user_and_admin(self) -> None:
        user = InviteCreate(email="a@example.com", role="user")
        admin = InviteCreate(email="b@example.com", role="admin")
        self.assertEqual(user.role, UserRole.USER)
        self.assertEqual(admin.role, UserRole.ADMIN)


class InviteIntegrityApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        database = Path(cls.tempdir.name) / "invites.db"
        cls.engine = create_async_engine(f"sqlite+aiosqlite:///{database}")

        @event.listens_for(cls.engine.sync_engine, "connect")
        def enable_foreign_keys(connection, _record) -> None:
            connection.execute("PRAGMA foreign_keys=ON")

        cls.sessions = async_sessionmaker(cls.engine, expire_on_commit=False)
        asyncio.run(cls._create_schema())

        app = FastAPI()
        app.include_router(invites_router.router)
        app.include_router(auth_router.router)

        async def override_db():
            async with cls.sessions() as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        cls.client = TestClient(app)
        cls.admin_token = create_access_token({"sub": "1"})

    @classmethod
    def tearDownClass(cls) -> None:
        asyncio.run(cls.engine.dispose())
        cls.tempdir.cleanup()

    @classmethod
    async def _create_schema(cls) -> None:
        async with cls.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with cls.sessions() as session:
            session.add(
                User(
                    id=1,
                    email="admin@example.com",
                    password_hash=get_password_hash("password123"),
                    role=UserRole.ADMIN,
                    is_active=True,
                )
            )
            await session.commit()

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.admin_token}"}

    def test_claim_invite_creates_pending_with_canonical(self) -> None:
        async def run() -> Invite:
            async with self.sessions() as session:
                invite = await claim_invite(
                    session,
                    email="  NewUser@Example.COM ",
                    role="user",
                    created_by_id=1,
                )
                await session.commit()
                await session.refresh(invite)
                return invite

        invite = asyncio.run(run())
        self.assertEqual(invite.email, "NewUser@Example.COM")
        self.assertEqual(invite.email_canonical, "newuser@example.com")
        self.assertEqual(invite.status, InviteStatus.PENDING)

    def test_claim_invite_rejects_existing_account_case_insensitive(self) -> None:
        async def run() -> None:
            async with self.sessions() as session:
                await claim_invite(
                    session,
                    email="ADMIN@example.com",
                    role="user",
                    created_by_id=1,
                )

        with self.assertRaises(InviteClaimError) as ctx:
            asyncio.run(run())
        self.assertIn("already exists", ctx.exception.detail)

    def test_claim_invite_uniqueness_pending(self) -> None:
        async def first() -> None:
            async with self.sessions() as session:
                await claim_invite(
                    session,
                    email="dup@example.com",
                    role="user",
                    created_by_id=1,
                )
                await session.commit()

        async def second() -> None:
            async with self.sessions() as session:
                await claim_invite(
                    session,
                    email="DUP@example.com",
                    role="admin",
                    created_by_id=1,
                )

        asyncio.run(first())
        with self.assertRaises(InviteClaimError) as ctx:
            asyncio.run(second())
        self.assertIn("already exists for this email", ctx.exception.detail)

    def test_reaper_flips_expired_pending(self) -> None:
        async def seed_and_reap() -> tuple[str, int]:
            async with self.sessions() as session:
                session.add(
                    Invite(
                        email="expired@example.com",
                        token="expired-token-1",
                        role="user",
                        status=InviteStatus.PENDING,
                        expiry_date=datetime.utcnow() - timedelta(hours=1),
                        created_by_id=1,
                    )
                )
                await session.commit()

            async with self.sessions() as session:
                n = await reap_expired_invites(session)
                await session.commit()
                invite = (
                    await session.execute(
                        select(Invite).where(
                            Invite.email_canonical == "expired@example.com"
                        )
                    )
                ).scalar_one()
                return invite.status, n

        status_value, n = asyncio.run(seed_and_reap())
        self.assertGreaterEqual(n, 1)
        self.assertEqual(status_value, InviteStatus.EXPIRED)

    def test_claim_after_expiry_allows_reinvite(self) -> None:
        async def run() -> Invite:
            async with self.sessions() as session:
                session.add(
                    Invite(
                        email="reinvite@example.com",
                        token="old-expired-token",
                        role="user",
                        status=InviteStatus.PENDING,
                        expiry_date=datetime.utcnow() - timedelta(days=1),
                        created_by_id=1,
                    )
                )
                await session.commit()

            async with self.sessions() as session:
                invite = await claim_invite(
                    session,
                    email="reinvite@example.com",
                    role="user",
                    created_by_id=1,
                )
                await session.commit()
                await session.refresh(invite)
                return invite

        invite = asyncio.run(run())
        self.assertEqual(invite.status, InviteStatus.PENDING)
        self.assertEqual(invite.email_canonical, "reinvite@example.com")

    def test_create_invite_endpoint_uses_claim(self) -> None:
        response = self.client.post(
            "/api/admin/invite-user",
            headers=self._auth(),
            json={"email": "endpoint@example.com", "role": "user"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["email"], "endpoint@example.com")
        self.assertEqual(body["status"], "pending")

        duplicate = self.client.post(
            "/api/admin/invite-user",
            headers=self._auth(),
            json={"email": "ENDPOINT@example.com", "role": "user"},
        )
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn("already", duplicate.json()["detail"].lower())

    def test_create_invite_rejects_invalid_role(self) -> None:
        response = self.client.post(
            "/api/admin/invite-user",
            headers=self._auth(),
            json={"email": "role@example.com", "role": "wizard"},
        )
        self.assertEqual(response.status_code, 422)

    def test_list_counts_exclude_expired_pending(self) -> None:
        async def seed() -> None:
            async with self.sessions() as session:
                session.add_all(
                    [
                        Invite(
                            email="count-pending@example.com",
                            token="count-pending-token",
                            role="user",
                            status=InviteStatus.PENDING,
                            expiry_date=datetime.utcnow() + timedelta(days=3),
                            created_by_id=1,
                        ),
                        Invite(
                            email="count-accepted@example.com",
                            token="count-accepted-token",
                            role="user",
                            status=InviteStatus.ACCEPTED,
                            expiry_date=datetime.utcnow() + timedelta(days=3),
                            created_by_id=1,
                        ),
                        Invite(
                            email="count-stale-pending@example.com",
                            token="count-stale-token",
                            role="user",
                            status=InviteStatus.PENDING,
                            expiry_date=datetime.utcnow() - timedelta(days=2),
                            created_by_id=1,
                        ),
                    ]
                )
                await session.commit()

        asyncio.run(seed())
        response = self.client.get("/api/admin/invites", headers=self._auth())
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertIn("accepted", body)
        self.assertIn("pending", body)
        self.assertGreaterEqual(body["accepted"], 1)
        # Reaper should have flipped the stale pending row; it must not inflate pending.
        async def stale_status() -> str:
            async with self.sessions() as session:
                invite = (
                    await session.execute(
                        select(Invite).where(
                            Invite.email_canonical == "count-stale-pending@example.com"
                        )
                    )
                ).scalar_one()
                return invite.status

        self.assertEqual(asyncio.run(stale_status()), InviteStatus.EXPIRED)

    def test_accept_flow_case_insensitive_login(self) -> None:
        create = self.client.post(
            "/api/admin/invite-user",
            headers=self._auth(),
            json={"email": "AcceptMe@Example.com", "role": "user"},
        )
        self.assertEqual(create.status_code, 200, create.text)
        token = create.json()["token"]

        accept = self.client.post(
            f"/api/accept-invite/{token}",
            json={"token": token, "password": "password123"},
        )
        self.assertEqual(accept.status_code, 200, accept.text)
        # EmailStr normalizes the domain; local-part casing is preserved.
        self.assertEqual(accept.json()["user"]["email"].lower(), "acceptme@example.com")

        login = self.client.post(
            "/api/auth/login",
            json={"email": "acceptme@example.com", "password": "password123"},
        )
        self.assertEqual(login.status_code, 200, login.text)
        self.assertIn("access_token", login.json())

    def test_check_invite_uses_canonical(self) -> None:
        self.client.post(
            "/api/admin/invite-user",
            headers=self._auth(),
            json={"email": "CheckCase@Example.com", "role": "admin"},
        )
        response = self.client.get("/api/check-invite/checkcase@example.com")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["has_invite"])
        self.assertEqual(body["role"], "admin")


if __name__ == "__main__":
    unittest.main()
