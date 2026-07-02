"""Owner-scoped Feedback Case history and detail."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.dependencies.auth import get_current_active_user
from backend.models.feedback_case import CaseReply, FeedbackCase
from backend.models.user import User
from backend.models.wiki import ChatMessage
from backend.services.redaction import project_text
from backend.services.features import require_feature


router = APIRouter(prefix="/api/feedback-cases", tags=["feedback-cases"])
MAX_REPLY_LENGTH = 4000


class ReplyCreate(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Reply cannot be empty")
        if len(stripped) > MAX_REPLY_LENGTH:
            raise ValueError(f"Reply must be at most {MAX_REPLY_LENGTH} characters")
        return stripped


def _summary(case: FeedbackCase) -> dict[str, Any]:
    feedback = case.feedback
    return {
        "case_id": case.public_id,
        "status": case.status,
        "categories": feedback.categories or [],
        "comment": feedback.message,
        "created_at": case.created_at.isoformat(),
        "updated_at": case.updated_at.isoformat(),
    }


async def _owned_case(
    db: AsyncSession,
    public_id: str,
    user_id: int,
) -> FeedbackCase:
    result = await db.execute(
        select(FeedbackCase)
        .options(
            selectinload(FeedbackCase.feedback),
            selectinload(FeedbackCase.replies),
        )
        .where(
            FeedbackCase.public_id == public_id,
            FeedbackCase.user_id == user_id,
        )
    )
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail="Feedback Case not found")
    return case


@router.get("")
async def list_feedback_cases(
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await require_feature(db, "tester_correspondence_enabled")
    query = (
        select(FeedbackCase)
        .options(selectinload(FeedbackCase.feedback))
        .where(FeedbackCase.user_id == current_user.id)
        .order_by(FeedbackCase.created_at.desc(), FeedbackCase.id.desc())
        .limit(limit + 1)
    )
    if cursor:
        cursor_case = await _owned_case(db, cursor, current_user.id)
        query = query.where(
            or_(
                FeedbackCase.created_at < cursor_case.created_at,
                and_(
                    FeedbackCase.created_at == cursor_case.created_at,
                    FeedbackCase.id < cursor_case.id,
                ),
            )
        )

    result = await db.execute(query)
    cases = list(result.scalars().unique())
    has_more = len(cases) > limit
    page = cases[:limit]
    return {
        "cases": [_summary(case) for case in page],
        "next_cursor": page[-1].public_id if has_more else None,
    }


@router.get("/{case_id}")
async def get_feedback_case(
    case_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await require_feature(db, "tester_correspondence_enabled")
    case = await _owned_case(db, case_id, current_user.id)
    rated = await db.get(ChatMessage, case.rated_message_id)
    if rated is None:
        raise HTTPException(status_code=404, detail="Feedback Case not found")

    result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.chat_session_id == case.chat_session_id,
            ChatMessage.role == "user",
            or_(
                ChatMessage.created_at < rated.created_at,
                and_(
                    ChatMessage.created_at == rated.created_at,
                    ChatMessage.id < rated.id,
                ),
            ),
        )
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(1)
    )
    question = result.scalar_one_or_none()
    return {
        **_summary(case),
        "rated_exchange": {
            "user": (
                {
                    "id": question.id,
                    "content": question.content,
                    "created_at": question.created_at.isoformat(),
                }
                if question
                else None
            ),
            "assistant": {
                "id": rated.id,
                "content": rated.content,
                "created_at": rated.created_at.isoformat(),
            },
        },
        "replies": [
            {
                "id": reply.id,
                "author_role": reply.author_role,
                "text": reply.raw_text,
                "created_at": reply.created_at.isoformat(),
            }
            for reply in case.replies
        ],
    }


@router.post("/{case_id}/replies", status_code=201)
async def reply_to_feedback_case(
    case_id: str,
    reply_data: ReplyCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await require_feature(db, "tester_correspondence_enabled")
    result = await db.execute(
        select(FeedbackCase)
        .where(
            FeedbackCase.public_id == case_id,
            FeedbackCase.user_id == current_user.id,
        )
        .with_for_update()
    )
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail="Feedback Case not found")

    reply = CaseReply(
        case_id=case.id,
        author_id=current_user.id,
        author_role="user",
        raw_text=reply_data.text,
    )
    db.add(reply)
    await db.flush()
    await project_text(
        db,
        content_type="case_reply",
        content_id=reply.id,
        source_field="raw_text",
        raw_text=reply.raw_text,
    )
    case.status = "awaiting_admin"
    await db.commit()
    return {
        "id": reply.id,
        "status": case.status,
        "created_at": reply.created_at.isoformat(),
    }
