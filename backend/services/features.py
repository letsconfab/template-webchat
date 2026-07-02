"""Feedback workflow feature gates and replay readiness."""

from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.chat import ChatSession
from backend.models.diagnostics import AdminProjection
from backend.models.feedback_case import CaseReply, FeedbackCase
from backend.models.settings import SystemSettings
from backend.models.wiki import ChatMessage
from backend.services.redaction import PROJECTION_VERSION


async def feature_enabled(db: AsyncSession, feature: str) -> bool:
    settings = (
        await db.execute(select(SystemSettings).limit(1))
    ).scalar_one_or_none()
    # Test/legacy databases without a settings row retain pre-flag behavior.
    return True if settings is None else bool(getattr(settings, feature))


async def require_feature(db: AsyncSession, feature: str) -> None:
    if not await feature_enabled(db, feature):
        raise HTTPException(status_code=404, detail="Feature not enabled")


async def admin_replay_readiness(db: AsyncSession) -> dict[str, int | bool]:
    unbound_legacy = (
        await db.execute(
            select(func.count(ChatMessage.id)).where(
                ChatMessage.chat_session_id.is_(None)
            )
        )
    ).scalar() or 0
    message_ids = select(ChatMessage.id).join(
        ChatSession,
        ChatSession.id == ChatMessage.chat_session_id,
    ).where(ChatSession.ownership_state == "owned")
    feedback_ids = select(FeedbackCase.feedback_id)
    reply_ids = select(CaseReply.id).where(CaseReply.author_role == "user")

    eligible_projected_content = (
        (await db.execute(select(func.count()).select_from(message_ids.subquery()))).scalar()
        or 0
    ) + (
        (await db.execute(select(func.count()).select_from(feedback_ids.subquery()))).scalar()
        or 0
    ) + (
        (await db.execute(select(func.count()).select_from(reply_ids.subquery()))).scalar()
        or 0
    )
    eligible = eligible_projected_content + unbound_legacy

    projections = (
        await db.execute(
            select(AdminProjection).where(
                AdminProjection.version == PROJECTION_VERSION,
                (
                    and_(
                        AdminProjection.content_type == "chat_message",
                        AdminProjection.content_id.in_(message_ids),
                    )
                    | and_(
                        AdminProjection.content_type == "feedback",
                        AdminProjection.content_id.in_(feedback_ids),
                    )
                    | and_(
                        AdminProjection.content_type == "case_reply",
                        AdminProjection.content_id.in_(reply_ids),
                    )
                ),
            )
        )
    ).scalars().all()
    succeeded = sum(item.status == "succeeded" for item in projections)
    failed = sum(item.status == "failed" for item in projections)
    explicit_pending = sum(item.status == "pending" for item in projections)
    missing = max(0, eligible_projected_content - len(projections))
    missing += unbound_legacy
    pending = explicit_pending + missing
    return {
        "eligible": eligible,
        "succeeded": succeeded,
        "failed": failed,
        "pending": pending,
        "ready": pending == 0,
    }
