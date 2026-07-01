"""User feedback router."""

from typing import Any, List, Optional
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.dependencies.auth import get_current_active_user, get_current_admin_user
from backend.models.user import User
from backend.models.chat import ChatSession
from backend.models.feedback_case import FeedbackCase
from backend.models.wiki import UserFeedback, ChatMessage
from backend.services.redaction import get_projection, mask_email, project_text


router = APIRouter(prefix="/api/feedback", tags=["feedback"])

ALLOWED_FEEDBACK_TYPES = {"thumbs_up", "thumbs_down"}
ALLOWED_CATEGORIES = {
    "inaccurate",
    "incomplete",
    "off_topic",
    "outdated",
    "too_long",
    "other",
}
MAX_COMMENT_LENGTH = 2000


def _validate_categories(categories: Optional[List[str]]) -> Optional[List[str]]:
    if categories is None:
        return None
    unknown = set(categories) - ALLOWED_CATEGORIES
    if unknown:
        raise ValueError(
            f"Unknown categories: {sorted(unknown)}. "
            f"Allowed: {sorted(ALLOWED_CATEGORIES)}"
        )
    return categories


def _validate_comment(message: Optional[str]) -> Optional[str]:
    if message is not None and len(message) > MAX_COMMENT_LENGTH:
        raise ValueError(f"Comment must be at most {MAX_COMMENT_LENGTH} characters")
    return message


class FeedbackCreate(BaseModel):
    rating: Optional[int] = None
    feedback_type: str  # 'thumbs_up' or 'thumbs_down'
    message: Optional[str] = None
    chat_message_id: Optional[int] = None
    categories: Optional[List[str]] = None

    @field_validator("feedback_type")
    @classmethod
    def check_feedback_type(cls, v: str) -> str:
        if v not in ALLOWED_FEEDBACK_TYPES:
            raise ValueError(
                f"feedback_type must be one of {sorted(ALLOWED_FEEDBACK_TYPES)}"
            )
        return v

    @field_validator("categories")
    @classmethod
    def check_categories(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        return _validate_categories(v)

    @field_validator("message")
    @classmethod
    def check_message(cls, v: Optional[str]) -> Optional[str]:
        return _validate_comment(v)


class FeedbackUpdate(BaseModel):
    rating: Optional[int] = None
    message: Optional[str] = None
    categories: Optional[List[str]] = None

    @field_validator("categories")
    @classmethod
    def check_categories(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        return _validate_categories(v)

    @field_validator("message")
    @classmethod
    def check_message(cls, v: Optional[str]) -> Optional[str]:
        return _validate_comment(v)


class FeedbackResponse(BaseModel):
    id: int
    user_id: int
    user_email: Optional[str] = None
    rating: Optional[int]
    feedback_type: str
    message: Optional[str]
    categories: Optional[List[str]] = None
    chat_message_id: Optional[int]
    created_at: str

    class Config:
        from_attributes = True


def _feedback_to_response(f: UserFeedback, user_email: Optional[str] = None) -> FeedbackResponse:
    return FeedbackResponse(
        id=f.id,
        user_id=f.user_id,
        user_email=user_email,
        rating=f.rating,
        feedback_type=f.feedback_type,
        message=f.message,
        categories=f.categories,
        chat_message_id=f.chat_message_id,
        created_at=f.created_at.isoformat(),
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_feedback(
    feedback_data: FeedbackCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Submit user feedback on chat response.

    If feedback for the same (user, chat_message_id) already exists, the
    existing row is updated instead — re-votes don't duplicate.
    """
    rated_message = None
    if feedback_data.chat_message_id is not None:
        result = await db.execute(
            select(ChatMessage)
            .join(
                ChatSession,
                ChatSession.id == ChatMessage.chat_session_id,
            )
            .where(
                ChatMessage.id == feedback_data.chat_message_id,
                ChatMessage.role == "assistant",
                ChatSession.user_id == current_user.id,
                ChatSession.ownership_state == "owned",
            )
            .with_for_update()
        )
        rated_message = result.scalar_one_or_none()
        if rated_message is None:
            raise HTTPException(status_code=404, detail="Chat message not found")
    elif feedback_data.feedback_type == "thumbs_down":
        raise HTTPException(
            status_code=422,
            detail="Negative feedback requires a rated assistant message",
        )

    db_feedback = None
    if rated_message is not None:
        result = await db.execute(
            select(UserFeedback).where(
                UserFeedback.user_id == current_user.id,
                UserFeedback.chat_message_id == rated_message.id,
            )
        )
        db_feedback = result.scalars().first()

    if db_feedback:
        db_feedback.feedback_type = feedback_data.feedback_type
        db_feedback.rating = feedback_data.rating
        if feedback_data.message is not None:
            db_feedback.message = feedback_data.message
        if feedback_data.categories is not None:
            db_feedback.categories = feedback_data.categories
    else:
        db_feedback = UserFeedback(
            user_id=current_user.id,
            rating=feedback_data.rating,
            feedback_type=feedback_data.feedback_type,
            message=feedback_data.message,
            categories=feedback_data.categories,
            chat_message_id=feedback_data.chat_message_id,
        )
        db.add(db_feedback)

    await db.flush()
    await project_text(
        db,
        content_type="feedback",
        content_id=db_feedback.id,
        source_field="message",
        raw_text=db_feedback.message,
    )
    case = None
    if feedback_data.feedback_type == "thumbs_down":
        result = await db.execute(
            select(FeedbackCase).where(
                FeedbackCase.feedback_id == db_feedback.id
            )
        )
        case = result.scalar_one_or_none()
        if case is None:
            case = FeedbackCase(
                public_id=str(uuid4()),
                feedback_id=db_feedback.id,
                user_id=current_user.id,
                chat_session_id=rated_message.chat_session_id,
                rated_message_id=rated_message.id,
                status="awaiting_admin",
            )
            db.add(case)

    await db.commit()
    await db.refresh(db_feedback)

    response = {
        "id": db_feedback.id,
        "message": "Feedback submitted successfully",
    }
    if case is not None:
        response["case_id"] = case.public_id
    return response


@router.patch("/{feedback_id}")
async def update_feedback(
    feedback_id: int,
    feedback_data: FeedbackUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Attach categories/comment/rating to existing feedback (owner only)."""
    result = await db.execute(
        select(UserFeedback).where(UserFeedback.id == feedback_id)
    )
    feedback = result.scalar_one_or_none()

    if not feedback:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found"
        )
    if feedback.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed to modify this feedback",
        )

    if feedback_data.rating is not None:
        feedback.rating = feedback_data.rating
    if feedback_data.message is not None:
        feedback.message = feedback_data.message
    if feedback_data.categories is not None:
        feedback.categories = feedback_data.categories

    await project_text(
        db,
        content_type="feedback",
        content_id=feedback.id,
        source_field="message",
        raw_text=feedback.message,
    )
    await db.commit()

    return {"id": feedback.id, "message": "Feedback updated successfully"}


@router.get("/admin")
async def get_all_feedback(
    skip: int = 0,
    limit: int = 50,
    feedback_type: Optional[str] = None,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Get all feedback (admin only)."""
    query = (
        select(UserFeedback)
        .options(selectinload(UserFeedback.user))
        .order_by(desc(UserFeedback.created_at))
    )
    count_query = select(func.count(UserFeedback.id))

    if feedback_type:
        query = query.where(UserFeedback.feedback_type == feedback_type)
        count_query = count_query.where(UserFeedback.feedback_type == feedback_type)

    total = (await db.execute(count_query)).scalar() or 0

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    feedbacks = result.scalars().all()

    return {
        "feedback": [
            _feedback_to_response(
                f,
                user_email=mask_email(f.user.email) if f.user else None,
            ).model_copy(
                update={
                    "message": (
                        await get_projection(
                            db,
                            content_type="feedback",
                            content_id=f.id,
                            source_field="message",
                        )
                    ).text
                }
            )
            for f in feedbacks
        ],
        "total": total,
    }


@router.get("/stats")
async def get_feedback_stats(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Get feedback statistics (admin only)."""
    from datetime import datetime, timedelta

    # Last 30 days stats
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    result = await db.execute(
        select(UserFeedback).where(UserFeedback.created_at >= thirty_days_ago)
    )
    all_feedback = result.scalars().all()

    positive = sum(1 for f in all_feedback if f.feedback_type == "thumbs_up")
    negative = sum(1 for f in all_feedback if f.feedback_type == "thumbs_down")
    total = len(all_feedback)

    category_counts: dict = {}
    for f in all_feedback:
        for cat in f.categories or []:
            category_counts[cat] = category_counts.get(cat, 0) + 1

    # Last 24 hours negative
    yesterday = datetime.utcnow() - timedelta(days=1)
    recent_negative = await db.execute(
        select(UserFeedback).where(
            UserFeedback.feedback_type == "thumbs_down",
            UserFeedback.created_at >= yesterday,
        )
    )
    recent_negative_count = len(recent_negative.scalars().all())

    return {
        "total": total,
        "positive": positive,
        "negative": negative,
        "positive_percentage": round(positive / total * 100, 1) if total > 0 else 0,
        "negative_percentage": round(negative / total * 100, 1) if total > 0 else 0,
        "recent_negative_count": recent_negative_count,
        "categories": category_counts,
    }


@router.get("/{feedback_id}/context")
async def get_feedback_context(
    feedback_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Get feedback with chat context (last 10 messages, admin only)."""
    result = await db.execute(
        select(UserFeedback)
        .options(selectinload(UserFeedback.user))
        .where(UserFeedback.id == feedback_id)
    )
    feedback = result.scalar_one_or_none()

    if not feedback:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found"
        )

    # Get chat context (last 10 messages from the rated message's session)
    messages: List[ChatMessage] = []
    if feedback.chat_message_id:
        msg_result = await db.execute(
            select(ChatMessage).where(ChatMessage.id == feedback.chat_message_id)
        )
        msg = msg_result.scalar_one_or_none()

        if msg:
            session_messages = await db.execute(
                select(ChatMessage)
                .where(ChatMessage.session_id == msg.session_id)
                .order_by(ChatMessage.created_at.desc())
                .limit(10)
            )
            messages = list(session_messages.scalars().all())

    feedback_projection = await get_projection(
        db,
        content_type="feedback",
        content_id=feedback.id,
        source_field="message",
    )
    projected_messages = []
    for message in reversed(messages):
        projection = await get_projection(
            db,
            content_type="chat_message",
            content_id=message.id,
            source_field="content",
        )
        projected_messages.append(
            {
                "role": message.role,
                "content": projection.text,
                "redaction_status": projection.status,
                "created_at": message.created_at.isoformat(),
            }
        )
    return {
        "feedback": _feedback_to_response(
            feedback,
            user_email=mask_email(feedback.user.email) if feedback.user else None,
        ).model_copy(update={"message": feedback_projection.text}),
        "messages": projected_messages,
    }
