"""Tests for admin analytics overview."""

from __future__ import annotations

import asyncio
import time
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
import tempfile

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.database import Base, get_db
from backend.models import invite, settings  # noqa: F401
from backend.models.chat import ChatSession
from backend.models.feedback_case import FeedbackCase  # noqa: F401
from backend.models.diagnostics import AdminProjection  # noqa: F401
from backend.models.user import User
from backend.models.wiki import ChatMessage, UserFeedback
from backend.routers import admin_analytics
from backend.routers import users as users_router  # noqa: F401 — auth deps need user lookup patterns
from backend.services.analytics import (
    bucket_timestamps,
    build_daily_series,
    summarize_feedback,
    zero_fill_days,
)
from backend.services.auth import create_access_token


class AnalyticsUnitTests(unittest.TestCase):
    def test_zero_fill_is_continuous(self) -> None:
        days = zero_fill_days(7, date(2026, 7, 16))
        self.assertEqual(len(days), 7)
        self.assertEqual(days[0], date(2026, 7, 10))
        self.assertEqual(days[-1], date(2026, 7, 16))

    def test_undated_counted_separately(self) -> None:
        counts, undated = bucket_timestamps(
            [None, datetime(2026, 7, 15, 12, 0, 0), None],
            days=7,
            today=date(2026, 7, 16),
        )
        self.assertEqual(undated, 2)
        self.assertEqual(counts.get("2026-07-15"), 1)

    def test_outside_window_excluded(self) -> None:
        counts, undated = bucket_timestamps(
            [datetime(2026, 1, 1), datetime(2026, 7, 16, 1, 0, 0)],
            days=7,
            today=date(2026, 7, 16),
        )
        self.assertEqual(undated, 0)
        self.assertEqual(counts, {"2026-07-16": 1})

    def test_partial_today_flag(self) -> None:
        series = build_daily_series(
            {"2026-07-16": 3},
            {},
            days=7,
            today=date(2026, 7, 16),
        )
        self.assertTrue(series[-1]["is_partial"])
        self.assertFalse(series[0]["is_partial"])
        self.assertEqual(series[-1]["messages"], 3)

    def test_feedback_summary(self) -> None:
        self.assertEqual(
            summarize_feedback(["thumbs_up", "thumbs_down", "thumbs_up", None]),
            {"thumbs_up": 2, "thumbs_down": 1},
        )


class AnalyticsApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        database = Path(cls.tempdir.name) / "analytics.db"
        cls.engine = create_async_engine(f"sqlite+aiosqlite:///{database}")

        @event.listens_for(cls.engine.sync_engine, "connect")
        def enable_foreign_keys(connection, _record) -> None:
            connection.execute("PRAGMA foreign_keys=ON")

        cls.sessions = async_sessionmaker(cls.engine, expire_on_commit=False)
        asyncio.run(cls._create_schema())
        app = FastAPI()
        app.include_router(admin_analytics.router)

        async def override_db():
            async with cls.sessions() as session:
                yield session

        app.dependency_overrides[get_db] = override_db
        cls.client = TestClient(app)
        cls.admin_token = create_access_token({"sub": "103"})
        cls.user_token = create_access_token({"sub": "101"})

    @classmethod
    async def _create_schema(cls) -> None:
        async with cls.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with cls.sessions() as session:
            session.add_all(
                [
                    User(
                        id=101,
                        email="user@example.test",
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
            await session.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        asyncio.run(cls.engine.dispose())
        cls.tempdir.cleanup()

    def _auth(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def test_rejects_non_admin(self) -> None:
        response = self.client.get(
            "/api/admin/analytics/overview",
            headers=self._auth(self.user_token),
        )
        self.assertEqual(response.status_code, 403)

    def test_rejects_invalid_days(self) -> None:
        response = self.client.get(
            "/api/admin/analytics/overview?days=14",
            headers=self._auth(self.admin_token),
        )
        self.assertEqual(response.status_code, 422)

    def test_overview_zero_fills_and_counts(self) -> None:
        today = date.today()
        async def seed() -> None:
            async with self.sessions() as session:
                session.add(
                    ChatSession(
                        client_uuid="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                        user_id=101,
                        created_at=datetime.combine(today, datetime.min.time()),
                        updated_at=datetime.combine(today, datetime.min.time()),
                    )
                )
                await session.flush()
                undated = ChatMessage(
                    session_id="s2",
                    role="user",
                    content="undated",
                )
                session.add_all(
                    [
                        ChatMessage(
                            session_id="s1",
                            role="user",
                            content="hi",
                            created_at=datetime.combine(today, datetime.min.time())
                            + timedelta(hours=1),
                        ),
                        ChatMessage(
                            session_id="s1",
                            role="assistant",
                            content="hello",
                            created_at=datetime.combine(today, datetime.min.time())
                            + timedelta(hours=2),
                        ),
                        undated,
                        UserFeedback(
                            user_id=101,
                            feedback_type="thumbs_up",
                            created_at=datetime.combine(today, datetime.min.time()),
                        ),
                        UserFeedback(
                            user_id=101,
                            feedback_type="thumbs_down",
                            created_at=datetime.combine(today, datetime.min.time()),
                        ),
                    ]
                )
                await session.flush()
                # Column default would fill created_at; force a true NULL for undated reporting
                undated.created_at = None
                await session.commit()

        asyncio.run(seed())
        response = self.client.get(
            "/api/admin/analytics/overview?days=7",
            headers=self._auth(self.admin_token),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["days"], 7)
        self.assertEqual(len(body["daily"]), 7)
        self.assertEqual(body["thumbs_up"], 1)
        self.assertEqual(body["thumbs_down"], 1)
        self.assertEqual(body["undated_messages"], 1)
        self.assertTrue(body["daily"][-1]["is_partial"])
        self.assertGreaterEqual(body["daily"][-1]["messages"], 2)
        self.assertGreaterEqual(body["daily"][-1]["sessions"], 1)

    def test_representative_volume_latency(self) -> None:
        """Assert row count and latency at a representative upper bound."""
        async def seed_volume() -> int:
            async with self.sessions() as session:
                rows = []
                base = datetime.utcnow() - timedelta(days=10)
                for i in range(5000):
                    rows.append(
                        ChatMessage(
                            session_id=f"vol-{i // 10}",
                            role="user" if i % 2 == 0 else "assistant",
                            content="x",
                            created_at=base + timedelta(minutes=i),
                        )
                    )
                session.add_all(rows)
                await session.commit()
                return len(rows)

        n = asyncio.run(seed_volume())
        self.assertEqual(n, 5000)
        started = time.perf_counter()
        response = self.client.get(
            "/api/admin/analytics/overview?days=30",
            headers=self._auth(self.admin_token),
        )
        elapsed = time.perf_counter() - started
        self.assertEqual(response.status_code, 200)
        # Soft bound: column-projected count of 5k rows should stay under 2s
        self.assertLess(elapsed, 2.0, f"analytics overview took {elapsed:.3f}s")


if __name__ == "__main__":
    unittest.main()
