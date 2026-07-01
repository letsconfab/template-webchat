"""Privacy and bounding tests for administrative diagnostics."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.database import Base, get_db
from backend.models import invite, settings  # noqa: F401
from backend.models.chat import ChatSession
from backend.models.diagnostics import AdminProjection
from backend.models.feedback_case import FeedbackCase
from backend.models.user import User
from backend.models.wiki import ChatMessage, UserFeedback
from backend.routers import admin_feedback_cases
from backend.services.auth import create_access_token
from backend.services.execution_traces import (
    ALLOWED_EVENT_KEYS,
    MAX_TRACE_BYTES,
    MAX_TRACE_EVENTS,
    bound_trace_events,
    persist_trace,
)
from backend.services.redaction import get_projection, project_text, redactor


class RedactionAndTraceTests(unittest.TestCase):
    def test_local_redaction_covers_structured_and_named_entities(self) -> None:
        raw = (
            "Jane Doe in New York can be reached at jane@example.com "
            "or 212-555-1234. Source: Jane Doe medical-record.pdf"
        )

        redacted = redactor.redact(raw)

        for secret in ("Jane Doe", "New York", "jane@example.com", "212-555-1234"):
            self.assertNotIn(secret, redacted)
        self.assertIn("<PERSON>", redacted)
        self.assertIn("<LOCATION>", redacted)

    def test_trace_is_ordered_bounded_and_drops_forbidden_fields(self) -> None:
        events = [
            {
                "sequence": index,
                "event_type": "tool_completed",
                "tool_name": "retrieve_knowledge",
                "summary": "x" * 10_000,
                "raw_input": "secret",
                "provider_payload": {"secret": True},
                "reasoning": "chain of thought",
            }
            for index in range(150)
        ]

        bounded, truncated, byte_size = bound_trace_events(events)

        self.assertTrue(truncated)
        self.assertLessEqual(len(bounded), MAX_TRACE_EVENTS)
        self.assertLessEqual(byte_size, MAX_TRACE_BYTES)
        self.assertEqual(
            [event["sequence"] for event in bounded],
            list(range(len(bounded))),
        )
        self.assertTrue(
            all(set(event).issubset(ALLOWED_EVENT_KEYS) for event in bounded)
        )
        serialized = json.dumps(bounded)
        for forbidden in ("secret", "provider_payload", "reasoning", "raw_input"):
            self.assertNotIn(forbidden, serialized)

    def test_projection_failure_is_fail_closed(self) -> None:
        async def scenario() -> tuple[str, str | None]:
            with tempfile.TemporaryDirectory() as directory:
                engine = create_async_engine(
                    f"sqlite+aiosqlite:///{Path(directory) / 'projection.db'}"
                )
                async with engine.begin() as connection:
                    await connection.run_sync(Base.metadata.create_all)
                sessions = async_sessionmaker(engine, expire_on_commit=False)
                original = redactor.redact
                redactor.redact = Mock(side_effect=RuntimeError("model unavailable"))
                try:
                    async with sessions() as session:
                        await project_text(
                            session,
                            content_type="chat_message",
                            content_id=99,
                            source_field="content",
                            raw_text="Raw secret jane@example.com",
                        )
                        await session.commit()
                    async with sessions() as session:
                        projection = await get_projection(
                            session,
                            content_type="chat_message",
                            content_id=99,
                            source_field="content",
                        )
                        return projection.status, projection.text
                finally:
                    redactor.redact = original
                    await engine.dispose()

        self.assertEqual(asyncio.run(scenario()), ("failed", None))


class AdminReplayApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        database = Path(cls.tempdir.name) / "replay.db"
        cls.engine = create_async_engine(f"sqlite+aiosqlite:///{database}")

        @event.listens_for(cls.engine.sync_engine, "connect")
        def enable_foreign_keys(connection, _record) -> None:
            connection.execute("PRAGMA foreign_keys=ON")

        cls.sessions = async_sessionmaker(cls.engine, expire_on_commit=False)
        cls.case_id = asyncio.run(cls._seed())
        app = FastAPI()
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
                id=201,
                email="private.person@example.test",
                password_hash="hash",
                role="user",
                is_active=True,
            )
            admin = User(
                id=202,
                email="admin@example.test",
                password_hash="hash",
                role="admin",
                is_active=True,
            )
            chat_session = ChatSession(
                client_uuid=str(uuid4()),
                user_id=201,
                ownership_state="owned",
            )
            session.add_all([owner, admin, chat_session])
            await session.flush()

            messages = []
            projections = []
            for index in range(105):
                message = ChatMessage(
                    chat_session_id=chat_session.id,
                    session_id=chat_session.client_uuid,
                    role="assistant" if index % 2 else "user",
                    content=f"RAW private.person@example.test message {index}",
                )
                session.add(message)
                await session.flush()
                messages.append(message)
                projections.append(
                    AdminProjection(
                        content_type="chat_message",
                        content_id=message.id,
                        source_field="content",
                        version=1,
                        status="failed" if index == 0 else "succeeded",
                        redacted_text=(
                            None if index == 0 else f"Redacted message {index}"
                        ),
                        safe_error_category=(
                            "redactor_unavailable" if index == 0 else None
                        ),
                    )
                )
            feedback = UserFeedback(
                user_id=owner.id,
                feedback_type="thumbs_down",
                rating=1,
                message="RAW private comment",
                categories=["inaccurate"],
                chat_message_id=messages[51].id,
            )
            session.add(feedback)
            await session.flush()
            case = FeedbackCase(
                public_id=str(uuid4()),
                feedback_id=feedback.id,
                user_id=owner.id,
                chat_session_id=chat_session.id,
                rated_message_id=messages[51].id,
                status="awaiting_admin",
            )
            session.add_all(
                [
                    case,
                    *projections,
                    AdminProjection(
                        content_type="feedback",
                        content_id=feedback.id,
                        source_field="message",
                        version=1,
                        status="succeeded",
                        redacted_text="Redacted comment",
                    ),
                ]
            )
            await session.flush()
            await persist_trace(
                session,
                chat_message_id=messages[51].id,
                events=[
                    {
                        "sequence": 0,
                        "event_type": "tool_started",
                        "tool_name": "retrieve_knowledge",
                    },
                    {
                        "sequence": 1,
                        "event_type": "tool_completed",
                        "tool_name": "retrieve_knowledge",
                        "duration_ms": 12,
                        "source_identifiers": ["<PERSON>.pdf"],
                        "result_count": 1,
                        "summary": "Tool completed with redacted results.",
                    },
                ],
            )
            await session.commit()
            return case.public_id

    @classmethod
    def tearDownClass(cls) -> None:
        asyncio.run(cls.engine.dispose())
        cls.tempdir.cleanup()

    @staticmethod
    def headers(user_id: int) -> dict[str, str]:
        token = create_access_token({"sub": str(user_id)})
        return {"Authorization": f"Bearer {token}"}

    def test_admin_replay_is_paginated_chronological_and_fail_closed(self) -> None:
        first = self.client.get(
            f"/api/admin/feedback-cases/{self.case_id}/replay",
            headers=self.headers(202),
        )
        second = self.client.get(
            f"/api/admin/feedback-cases/{self.case_id}/replay",
            params={"cursor": first.json()["next_cursor"]},
            headers=self.headers(202),
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(len(first.json()["messages"]), 100)
        self.assertEqual(len(second.json()["messages"]), 5)
        combined = first.json()["messages"] + second.json()["messages"]
        self.assertEqual(
            [message["id"] for message in combined],
            sorted(message["id"] for message in combined),
        )
        self.assertIsNone(combined[0]["content"])
        self.assertEqual(combined[0]["redaction_status"], "failed")
        self.assertNotIn("RAW", json.dumps(first.json()))
        self.assertNotIn("private.person@example.test", json.dumps(first.json()))

        rated = next(message for message in combined if message["is_rated"])
        self.assertEqual(rated["execution_trace"]["status"], "succeeded")
        self.assertEqual(
            [event["sequence"] for event in rated["execution_trace"]["events"]],
            [0, 1],
        )
        historical = next(
            message
            for message in combined
            if message["role"] == "assistant" and not message["is_rated"]
        )
        self.assertEqual(
            historical["execution_trace"]["status"],
            "not_captured",
        )
        self.assertTrue(any(message["is_post_feedback"] for message in combined))

    def test_admin_list_masks_email_and_non_admin_is_forbidden(self) -> None:
        admin = self.client.get(
            "/api/admin/feedback-cases",
            headers=self.headers(202),
        )
        tester = self.client.get(
            "/api/admin/feedback-cases",
            headers=self.headers(201),
        )

        self.assertEqual(admin.status_code, 200)
        masked = admin.json()["cases"][0]["account_email"]
        self.assertNotEqual(masked, "private.person@example.test")
        self.assertTrue(masked.endswith("@example.test"))
        self.assertEqual(tester.status_code, 403)


if __name__ == "__main__":
    unittest.main()
