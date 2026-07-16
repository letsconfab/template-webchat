"""Admin analytics overview endpoint."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies.auth import get_current_admin_user
from backend.models.chat import ChatSession
from backend.models.user import User
from backend.models.wiki import ChatMessage, UserFeedback
from backend.services.analytics import (
    ALLOWED_DAYS,
    bucket_timestamps,
    build_daily_series,
    summarize_feedback,
    utc_today,
    window_start,
)

router = APIRouter(prefix="/api/admin/analytics", tags=["admin-analytics"])


class DailyBucket(BaseModel):
    date: str
    messages: int
    sessions: int
    is_partial: bool


class AnalyticsOverview(BaseModel):
    days: Literal[7, 30, 90]
    thumbs_up: int
    thumbs_down: int
    undated_messages: int
    undated_sessions: int
    undated_feedback: int
    daily: list[DailyBucket] = Field(default_factory=list)


@router.get("/overview", response_model=AnalyticsOverview)
async def get_analytics_overview(
    days: int = Query(30),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    if days not in ALLOWED_DAYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"days must be one of {sorted(ALLOWED_DAYS)}",
        )

    today = utc_today()
    start = window_start(days, today)

    # Column-projected fetches only — never materialize message bodies.
    msg_result = await db.execute(
        select(ChatMessage.created_at).where(
            (ChatMessage.created_at >= start) | (ChatMessage.created_at.is_(None))
        )
    )
    message_timestamps = [row[0] for row in msg_result.all()]

    session_result = await db.execute(
        select(ChatSession.created_at).where(
            (ChatSession.created_at >= start) | (ChatSession.created_at.is_(None))
        )
    )
    session_timestamps = [row[0] for row in session_result.all()]

    feedback_result = await db.execute(
        select(UserFeedback.feedback_type, UserFeedback.created_at).where(
            (UserFeedback.created_at >= start) | (UserFeedback.created_at.is_(None))
        )
    )
    feedback_rows = feedback_result.all()

    # Feedback in window (dated) + undated tracked separately
    dated_types: list[str | None] = []
    undated_feedback = 0
    for feedback_type, created_at in feedback_rows:
        if created_at is None:
            undated_feedback += 1
            continue
        if created_at >= start:
            dated_types.append(feedback_type)

    thumbs = summarize_feedback(dated_types)
    msg_counts, undated_messages = bucket_timestamps(message_timestamps, days, today)
    sess_counts, undated_sessions = bucket_timestamps(session_timestamps, days, today)
    daily = build_daily_series(msg_counts, sess_counts, days, today)

    return AnalyticsOverview(
        days=days,  # type: ignore[arg-type]
        thumbs_up=thumbs["thumbs_up"],
        thumbs_down=thumbs["thumbs_down"],
        undated_messages=undated_messages,
        undated_sessions=undated_sessions,
        undated_feedback=undated_feedback,
        daily=[DailyBucket(**b) for b in daily],
    )
