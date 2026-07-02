"""Resumable conservative legacy ownership, case, and redaction backfill."""

from __future__ import annotations

from collections import Counter
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import distinct, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.models.chat import ChatSession
from backend.models.feedback_case import CaseReply, FeedbackCase
from backend.models.wiki import ChatMessage, UserFeedback
from backend.services.features import admin_replay_readiness
from backend.services.redaction import project_text


async def run_feedback_backfill(session_factory: async_sessionmaker) -> dict[str, int]:
    counts: Counter[str] = Counter()

    async with session_factory() as db:
        legacy_ids = list(
            (
                await db.execute(
                    select(distinct(ChatMessage.session_id)).where(
                        ChatMessage.chat_session_id.is_(None)
                    )
                )
            ).scalars()
        )

    for legacy_id in legacy_ids:
        async with session_factory() as db:
            try:
                messages = list(
                    (
                        await db.execute(
                            select(ChatMessage).where(
                                ChatMessage.session_id == legacy_id,
                                ChatMessage.chat_session_id.is_(None),
                            )
                        )
                    ).scalars()
                )
                message_ids = [message.id for message in messages]
                owners = set(
                    (
                        await db.execute(
                            select(distinct(UserFeedback.user_id)).where(
                                UserFeedback.chat_message_id.in_(message_ids)
                            )
                        )
                    ).scalars()
                )
                owned = len(owners) == 1
                owner_id = next(iter(owners)) if owned else None
                public_id = str(uuid5(NAMESPACE_URL, f"legacy-chat:{legacy_id}"))
                chat_session = (
                    await db.execute(
                        select(ChatSession).where(
                            ChatSession.client_uuid == public_id
                        )
                    )
                ).scalar_one_or_none()
                if chat_session is None:
                    chat_session = ChatSession(
                        client_uuid=public_id,
                        user_id=owner_id,
                        ownership_state="owned" if owned else "quarantined",
                    )
                    db.add(chat_session)
                    await db.flush()
                await db.execute(
                    update(ChatMessage)
                    .where(ChatMessage.id.in_(message_ids))
                    .values(chat_session_id=chat_session.id)
                )
                counts["processed"] += 1
                if not owned:
                    counts["quarantined"] += 1
                await db.commit()
            except Exception:
                await db.rollback()
                counts["failed"] += 1

    # Case creation is independently resumable after ownership binding.
    async with session_factory() as db:
        negative_feedback = list(
            (
                await db.execute(
                    select(UserFeedback, ChatMessage, ChatSession)
                    .join(ChatMessage, ChatMessage.id == UserFeedback.chat_message_id)
                    .join(
                        ChatSession,
                        ChatSession.id == ChatMessage.chat_session_id,
                    )
                    .where(
                        UserFeedback.feedback_type == "thumbs_down",
                        ChatSession.ownership_state == "owned",
                        ChatSession.user_id == UserFeedback.user_id,
                    )
                )
            ).all()
        )
        for feedback, message, chat_session in negative_feedback:
            existing = (
                await db.execute(
                    select(FeedbackCase).where(
                        FeedbackCase.feedback_id == feedback.id
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                db.add(
                    FeedbackCase(
                        public_id=str(uuid4()),
                        feedback_id=feedback.id,
                        user_id=feedback.user_id,
                        chat_session_id=chat_session.id,
                        rated_message_id=message.id,
                        status="awaiting_admin",
                    )
                )
                counts["processed"] += 1
        await db.commit()

    # Re-run missing or failed projections safely; historical traces remain absent.
    async with session_factory() as db:
        messages = list(
            (
                await db.execute(
                    select(ChatMessage)
                    .join(
                        ChatSession,
                        ChatSession.id == ChatMessage.chat_session_id,
                    )
                    .where(ChatSession.ownership_state == "owned")
                )
            ).scalars()
        )
        case_feedback = list(
            (
                await db.execute(
                    select(UserFeedback).join(
                        FeedbackCase,
                        FeedbackCase.feedback_id == UserFeedback.id,
                    )
                )
            ).scalars()
        )
        user_replies = list(
            (
                await db.execute(
                    select(CaseReply).where(CaseReply.author_role == "user")
                )
            ).scalars()
        )
        projection_inputs = [
            ("chat_message", item.id, "content", item.content) for item in messages
        ] + [
            ("feedback", item.id, "message", item.message) for item in case_feedback
        ] + [
            ("case_reply", item.id, "raw_text", item.raw_text)
            for item in user_replies
        ]
        for content_type, content_id, source_field, text in projection_inputs:
            projection = await project_text(
                db,
                content_type=content_type,
                content_id=content_id,
                source_field=source_field,
                raw_text=text,
            )
            counts["processed"] += 1
            counts[projection.status] += 1
        await db.commit()
        readiness = await admin_replay_readiness(db)

    counts["pending"] = int(readiness["pending"])
    counts.setdefault("succeeded", 0)
    counts.setdefault("failed", 0)
    counts.setdefault("quarantined", 0)
    return {
        key: counts[key]
        for key in ("processed", "succeeded", "failed", "quarantined", "pending")
    }

