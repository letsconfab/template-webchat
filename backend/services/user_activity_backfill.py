"""Resumable backfill of inferred_last_activity_at from recorded activity.

Per user, takes the max of:
- chat_sessions.updated_at
- user_feedback.created_at
- chat_messages.created_at joined through chat_sessions

Batched, incrementally committed, and safe to re-run.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.models.chat import ChatSession
from backend.models.user import User
from backend.models.wiki import ChatMessage, UserFeedback

DEFAULT_BATCH_SIZE = 100


async def _activity_for_user(db, user_id: int) -> Optional[datetime]:
    session_max = await db.scalar(
        select(func.max(ChatSession.updated_at)).where(ChatSession.user_id == user_id)
    )
    feedback_max = await db.scalar(
        select(func.max(UserFeedback.created_at)).where(UserFeedback.user_id == user_id)
    )
    message_max = await db.scalar(
        select(func.max(ChatMessage.created_at))
        .select_from(ChatMessage)
        .join(ChatSession, ChatSession.id == ChatMessage.chat_session_id)
        .where(ChatSession.user_id == user_id)
    )
    candidates = [ts for ts in (session_max, feedback_max, message_max) if ts is not None]
    return max(candidates) if candidates else None


async def run_user_activity_backfill(
    session_factory: async_sessionmaker,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, int]:
    counts: Counter[str] = Counter()

    async with session_factory() as db:
        user_ids = list((await db.execute(select(User.id).order_by(User.id))).scalars())

    for start in range(0, len(user_ids), batch_size):
        batch = user_ids[start : start + batch_size]
        async with session_factory() as db:
            try:
                for user_id in batch:
                    activity = await _activity_for_user(db, user_id)
                    user = (
                        await db.execute(select(User).where(User.id == user_id))
                    ).scalar_one()
                    if activity is None:
                        counts["skipped_no_activity"] += 1
                        continue
                    user.inferred_last_activity_at = activity
                    counts["updated"] += 1
                await db.commit()
                counts["batches"] += 1
            except Exception:
                await db.rollback()
                counts["failed"] += 1

    counts.setdefault("updated", 0)
    counts.setdefault("skipped_no_activity", 0)
    counts.setdefault("failed", 0)
    counts.setdefault("batches", 0)
    counts["processed"] = len(user_ids)
    return {
        key: counts[key]
        for key in ("processed", "updated", "skipped_no_activity", "failed", "batches")
    }
