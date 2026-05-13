"""User feedback router."""

from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.dependencies.auth import get_current_active_user
from backend.models.user import User
from backend.models.wiki import UserFeedback, ChatMessage


router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class FeedbackCreate(BaseModel):
    rating: Optional[int] = None
    feedback_type: str  # 'thumbs_up' or 'thumbs_down'
    message: Optional[str] = None
    chat_message_id: Optional[int] = None


class FeedbackResponse(BaseModel):
    id: int
    user_id: int
    rating: Optional[int]
    feedback_type: str
    message: Optional[str]
    chat_message_id: Optional[int]
    created_at: str

    class Config:
        from_attributes = True


class ChatContextResponse(BaseModel):
    feedback: FeedbackResponse
    messages: List[dict]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_feedback(
    feedback_data: FeedbackCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Submit user feedback on chat response."""
    db_feedback = UserFeedback(
        user_id=current_user.id,
        rating=feedback_data.rating,
        feedback_type=feedback_data.feedback_type,
        message=feedback_data.message,
        chat_message_id=feedback_data.chat_message_id,
    )
    db.add(db_feedback)
    await db.commit()
    await db.refresh(db_feedback)

    return {"id": db_feedback.id, "message": "Feedback submitted successfully"}


@router.get("/admin", response_model=List[FeedbackResponse])
async def get_all_feedback(
    skip: int = 0,
    limit: int = 50,
    feedback_type: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Get all feedback (admin only)."""
    query = (
        select(UserFeedback)
        .options(selectinload(UserFeedback.user))
        .order_by(desc(UserFeedback.created_at))
    )

    if feedback_type:
        query = query.where(UserFeedback.feedback_type == feedback_type)

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    feedbacks = result.scalars().all()

    return [
        FeedbackResponse(
            id=f.id,
            user_id=f.user_id,
            rating=f.rating,
            feedback_type=f.feedback_type,
            message=f.message,
            chat_message_id=f.chat_message_id,
            created_at=f.created_at.isoformat(),
        )
        for f in feedbacks
    ]


@router.get("/{feedback_id}/context")
async def get_feedback_context(
    feedback_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Get feedback with chat context (last 10 messages)."""
    result = await db.execute(
        select(UserFeedback).where(UserFeedback.id == feedback_id)
    )
    feedback = result.scalar_one_or_none()

    if not feedback:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found"
        )

    # Get chat context (last 10 messages for this user's session)
    if feedback.chat_message_id:
        # Get the message and find session
        msg_result = await db.execute(
            select(ChatMessage).where(ChatMessage.id == feedback.chat_message_id)
        )
        msg = msg_result.scalar_one_or_none()

        if msg:
            # Get last 10 messages from this session
            session_messages = await db.execute(
                select(ChatMessage)
                .where(ChatMessage.session_id == msg.session_id)
                .order_by(ChatMessage.created_at.desc())
                .limit(10)
            )
            messages = session_messages.scalars().all()

    return {
        "feedback": FeedbackResponse(
            id=feedback.id,
            user_id=feedback.user_id,
            rating=feedback.rating,
            feedback_type=feedback.feedback_type,
            message=feedback.message,
            chat_message_id=feedback.chat_message_id,
            created_at=feedback.created_at.isoformat(),
        ),
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat(),
            }
            for m in reversed(messages)
        ]
        if "messages" in locals()
        else [],
    }


@router.get("/stats")
async def get_feedback_stats(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Get feedback statistics."""
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
    }
