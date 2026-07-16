"""Bulk invite state machine, lease, cancel, and worker tests (PR 5).

SQLite exercises the state machine and lease claim path. Concurrent claim
exclusivity under load is a Postgres property and is not asserted here.
"""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.database import Base, get_db
from backend.models import bulk_invite as bulk_invite_models  # noqa: F401
from backend.models import invite as invite_models  # noqa: F401
from backend.models import settings as settings_models  # noqa: F401
from backend.models.bulk_invite import (
    BulkInviteRecipient,
    InviteBatch,
    InviteBatchState,
    RecipientState,
)
from backend.models.chat import ChatSession  # noqa: F401
from backend.models.diagnostics import AdminProjection  # noqa: F401
from backend.models.feedback_case import FeedbackCase  # noqa: F401
from backend.models.settings import SystemSettings
from backend.models.user import User, UserRole
from backend.models.wiki import ChatMessage, UserFeedback  # noqa: F401
from backend.routers import bulk_invites as bulk_invites_router
from backend.services.auth import create_access_token, get_password_hash
from backend.services.bulk_invites import (
    BulkInviteWorker,
    claim_recipient,
    enqueue_batch,
    extract_email,
    parse_csv_bytes,
    preview_csv,
    reap_expired_leases,
    refresh_batch_counts,
)


def _csv(*lines: str) -> bytes:
    return ("\n".join(lines) + "\n").encode("utf-8")


class CsvParseUnitTests(unittest.TestCase):
    def test_extract_angle_address(self) -> None:
        self.assertEqual(extract_email("Bob <bob@x.com>"), "bob@x.com")

    def test_header_and_email_column(self) -> None:
        rows = parse_csv_bytes(_csv("name,email", "Ada,ada@example.com"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].email_canonical, "ada@example.com")
        self.assertEqual(rows[0].line_number, 2)

    def test_no_header_single_column(self) -> None:
        rows = parse_csv_bytes(_csv("ada@example.com", "bob@example.com"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].line_number, 1)


class BulkInviteServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        database = Path(cls.tempdir.name) / "bulk.db"
        cls.engine = create_async_engine(f"sqlite+aiosqlite:///{database}")

        @event.listens_for(cls.engine.sync_engine, "connect")
        def enable_foreign_keys(connection, _record) -> None:
            connection.execute("PRAGMA foreign_keys=ON")

        cls.sessions = async_sessionmaker(cls.engine, expire_on_commit=False)
        asyncio.run(cls._create_schema())

        app = FastAPI()
        app.include_router(bulk_invites_router.router)

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
            session.add(
                SystemSettings(
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
                    admin_replay_enabled=True,
                    tester_correspondence_enabled=True,
                    tester_email_notifications_enabled=True,
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
            )
            await session.commit()

    def setUp(self) -> None:
        asyncio.run(self._clear_batches())

    async def _clear_batches(self) -> None:
        async with self.sessions() as session:
            for row in (
                await session.execute(select(BulkInviteRecipient))
            ).scalars():
                await session.delete(row)
            for row in (await session.execute(select(InviteBatch))).scalars():
                await session.delete(row)
            await session.commit()

    def _auth(self) -> dict:
        return {"Authorization": f"Bearer {self.admin_token}"}

    def test_preview_breakdown(self) -> None:
        async def seed_user():
            async with self.sessions() as session:
                session.add(
                    User(
                        email="existing@example.com",
                        password_hash=get_password_hash("x"),
                        role=UserRole.USER,
                        is_active=True,
                    )
                )
                await session.commit()

        asyncio.run(seed_user())
        content = _csv(
            "email",
            "new@example.com",
            "existing@example.com",
            "new@example.com",
            "not-an-email",
            "Bob <bob@example.com>",
        )
        async def run():
            async with self.sessions() as session:
                return await preview_csv(
                    session, content=content, filename="t.csv", role="user"
                )

        preview = asyncio.run(run())
        self.assertEqual(preview.will_invite.__len__(), 2)
        self.assertEqual(preview.already_registered.__len__(), 1)
        self.assertEqual(preview.duplicate_rows.__len__(), 1)
        self.assertEqual(preview.invalid_rows.__len__(), 1)

    def test_confirm_returns_202_and_does_not_send(self) -> None:
        transport = AsyncMock()
        content = _csv("email", "one@example.com", "two@example.com")
        response = self.client.post(
            "/api/admin/bulk-invites/confirm",
            headers=self._auth(),
            files={"file": ("invites.csv", content, "text/csv")},
            data={"role": "user"},
        )
        self.assertEqual(response.status_code, 202, response.text)
        self.assertIn("batch_id", response.json())
        transport.assert_not_called()

    def test_refuse_enqueue_without_email_config(self) -> None:
        async def clear_smtp():
            async with self.sessions() as session:
                settings = (
                    await session.execute(select(SystemSettings).limit(1))
                ).scalar_one()
                settings.smtp_server = None
                await session.commit()

        async def restore_smtp():
            async with self.sessions() as session:
                settings = (
                    await session.execute(select(SystemSettings).limit(1))
                ).scalar_one()
                settings.smtp_server = "smtp.example.test"
                await session.commit()

        asyncio.run(clear_smtp())
        try:
            response = self.client.post(
                "/api/admin/bulk-invites/confirm",
                headers=self._auth(),
                files={
                    "file": (
                        "invites.csv",
                        _csv("email", "a@example.com"),
                        "text/csv",
                    )
                },
                data={"role": "user"},
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn("not configured", response.json()["detail"].lower())
        finally:
            asyncio.run(restore_smtp())

    def test_transport_succeeds_commit_fails_lands_unknown_delivery(self) -> None:
        """At-least-once window: SMTP ok, commit fails → reaper, never silent re-send."""

        async def run() -> None:
            async with self.sessions() as session:
                batch = await enqueue_batch(
                    session,
                    content=_csv("email", "window@example.com"),
                    filename="w.csv",
                    role="user",
                    created_by_id=1,
                )
                await session.commit()
                batch_id = batch.id
                recipient = (
                    await session.execute(
                        select(BulkInviteRecipient).where(
                            BulkInviteRecipient.batch_id == batch_id
                        )
                    )
                ).scalar_one()
                recipient_id = recipient.id

            send_count = {"n": 0}

            async def transport(**_kwargs):
                send_count["n"] += 1

            worker = BulkInviteWorker(
                self.sessions,
                worker_id="test-worker",
                transport=transport,
                pace_seconds=0,
                fail_success_commit=True,
            )
            with self.assertRaises(RuntimeError):
                await worker.process_one()
            self.assertEqual(send_count["n"], 1)

            async with self.sessions() as session:
                row = (
                    await session.execute(
                        select(BulkInviteRecipient).where(
                            BulkInviteRecipient.id == recipient_id
                        )
                    )
                ).scalar_one()
                # Still sending — commit of SENT never landed.
                self.assertEqual(row.state, RecipientState.SENDING.value)
                await session.execute(
                    update(BulkInviteRecipient)
                    .where(BulkInviteRecipient.id == recipient_id)
                    .values(
                        lease_expires_at=datetime.utcnow() - timedelta(seconds=1)
                    )
                )
                await session.commit()
                reaped = await reap_expired_leases(session)
                self.assertEqual(reaped, 1)
                await refresh_batch_counts(session, batch_id)
                await session.commit()

            # A healthy worker must not re-send unknown_delivery.
            worker2 = BulkInviteWorker(
                self.sessions,
                worker_id="resume-worker",
                transport=transport,
                pace_seconds=0,
            )
            await worker2.process_one()
            await worker2.process_one()
            self.assertEqual(send_count["n"], 1)

            async with self.sessions() as session:
                row = (
                    await session.execute(
                        select(BulkInviteRecipient).where(
                            BulkInviteRecipient.id == recipient_id
                        )
                    )
                ).scalar_one()
                self.assertEqual(row.state, RecipientState.UNKNOWN_DELIVERY.value)

        asyncio.run(run())

    def test_cancel_racing_a_claim(self) -> None:
        async def run() -> None:
            async with self.sessions() as session:
                batch = await enqueue_batch(
                    session,
                    content=_csv("email", "race1@example.com", "race2@example.com"),
                    filename="race.csv",
                    role="user",
                    created_by_id=1,
                )
                await session.commit()
                batch_id = batch.id
                ids = list(
                    (
                        await session.execute(
                            select(BulkInviteRecipient.id)
                            .where(BulkInviteRecipient.batch_id == batch_id)
                            .order_by(BulkInviteRecipient.id)
                        )
                    ).scalars()
                )

            # Claim first recipient successfully.
            async with self.sessions() as session:
                won = await claim_recipient(
                    session, recipient_id=ids[0], worker_id="w1"
                )
                self.assertTrue(won)

            # Cancel: only unclaimed (pending) should cancel.
            response = self.client.post(
                f"/api/admin/bulk-invites/{batch_id}/cancel",
                headers=self._auth(),
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["state"], "cancelled")

            async with self.sessions() as session:
                rows = (
                    await session.execute(
                        select(BulkInviteRecipient)
                        .where(BulkInviteRecipient.batch_id == batch_id)
                        .order_by(BulkInviteRecipient.id)
                    )
                ).scalars().all()
                self.assertEqual(rows[0].state, RecipientState.SENDING.value)
                self.assertEqual(rows[1].state, RecipientState.CANCELLED.value)

                # Further claim of cancelled pending must fail (already cancelled).
                lost = await claim_recipient(
                    session, recipient_id=ids[1], worker_id="w2"
                )
                self.assertFalse(lost)

        asyncio.run(run())

    def test_lease_expiry_reaping_unknown_delivery(self) -> None:
        async def run() -> None:
            async with self.sessions() as session:
                batch = await enqueue_batch(
                    session,
                    content=_csv("email", "lease@example.com"),
                    filename="lease.csv",
                    role="user",
                    created_by_id=1,
                )
                await session.commit()
                recipient = (
                    await session.execute(
                        select(BulkInviteRecipient).where(
                            BulkInviteRecipient.batch_id == batch.id
                        )
                    )
                ).scalar_one()
                await claim_recipient(
                    session, recipient_id=recipient.id, worker_id="w"
                )
                await session.execute(
                    update(BulkInviteRecipient)
                    .where(BulkInviteRecipient.id == recipient.id)
                    .values(
                        lease_expires_at=datetime.utcnow() - timedelta(seconds=5)
                    )
                )
                await session.commit()
                n = await reap_expired_leases(session)
                await session.commit()
                self.assertEqual(n, 1)
                row = (
                    await session.execute(
                        select(BulkInviteRecipient).where(
                            BulkInviteRecipient.id == recipient.id
                        )
                    )
                ).scalar_one()
                self.assertEqual(row.state, RecipientState.UNKNOWN_DELIVERY.value)

        asyncio.run(run())

    def test_batch_resume_after_worker_restart(self) -> None:
        async def run() -> None:
            sent: list[str] = []

            async def transport(*, recipient: str, **_kwargs):
                sent.append(recipient)

            async with self.sessions() as session:
                batch = await enqueue_batch(
                    session,
                    content=_csv(
                        "email",
                        "resume1@example.com",
                        "resume2@example.com",
                    ),
                    filename="resume.csv",
                    role="user",
                    created_by_id=1,
                )
                await session.commit()
                batch_id = batch.id

            worker_a = BulkInviteWorker(
                self.sessions,
                worker_id="restart-a",
                transport=transport,
                pace_seconds=0,
            )
            self.assertTrue(await worker_a.process_one())
            # Simulate process death: new worker instance (restart).
            worker_b = BulkInviteWorker(
                self.sessions,
                worker_id="restart-b",
                transport=transport,
                pace_seconds=0,
            )
            self.assertTrue(await worker_b.process_one())

            self.assertEqual(len(sent), 2)
            async with self.sessions() as session:
                await refresh_batch_counts(session, batch_id)
                await session.commit()
                batch = (
                    await session.execute(
                        select(InviteBatch).where(InviteBatch.id == batch_id)
                    )
                ).scalar_one()
                self.assertEqual(batch.sent_count, 2)
                self.assertEqual(batch.state, InviteBatchState.COMPLETED.value)

        asyncio.run(run())

    def test_successful_send_marks_sent(self) -> None:
        async def run() -> None:
            transport = AsyncMock()
            async with self.sessions() as session:
                batch = await enqueue_batch(
                    session,
                    content=_csv("email", "ok@example.com"),
                    filename="ok.csv",
                    role="user",
                    created_by_id=1,
                )
                await session.commit()
                batch_id = batch.id

            worker = BulkInviteWorker(
                self.sessions, worker_id="ok", transport=transport, pace_seconds=0
            )
            self.assertTrue(await worker.process_one())
            transport.assert_awaited()
            async with self.sessions() as session:
                row = (
                    await session.execute(
                        select(BulkInviteRecipient).where(
                            BulkInviteRecipient.batch_id == batch_id
                        )
                    )
                ).scalar_one()
                self.assertEqual(row.state, RecipientState.SENT.value)
                self.assertIsNotNone(row.invite_id)

        asyncio.run(run())

    def test_start_once_guard(self) -> None:
        async def run() -> None:
            worker = BulkInviteWorker(self.sessions, worker_id="guard")
            self.assertTrue(worker.start_once())
            self.assertFalse(worker.start_once())
            await worker.stop()

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
