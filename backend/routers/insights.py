"""Knowledge insights router."""

from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.dependencies.auth import get_current_active_user
from backend.models.user import User
from backend.models.wiki import KnowledgeInsight


router = APIRouter(prefix="/api/insights", tags=["insights"])


class InsightResponse(BaseModel):
    id: int
    title: Optional[str]
    content: str
    source_type: str
    source_user_id: Optional[int]
    chat_session_id: Optional[str]
    status: str
    tags: Optional[list]
    created_at: str

    class Config:
        from_attributes = True


class InsightCreate(BaseModel):
    title: Optional[str] = None
    content: str
    source_type: str = "admin_created"
    tags: Optional[List[str]] = None


class InsightUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[List[str]] = None


@router.get("", response_model=List[InsightResponse])
async def get_insights(
    skip: int = 0,
    limit: int = 50,
    status_filter: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Get pending insights for review (admin only)."""
    query = (
        select(KnowledgeInsight)
        .options(selectinload(KnowledgeInsight.source_user))
        .order_by(desc(KnowledgeInsight.created_at))
    )

    if status_filter:
        query = query.where(KnowledgeInsight.status == status_filter)
    else:
        query = query.where(KnowledgeInsight.status == "pending")

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    insights = result.scalars().all()

    return [
        InsightResponse(
            id=i.id,
            title=i.title,
            content=i.content,
            source_type=i.source_type,
            source_user_id=i.source_user_id,
            chat_session_id=i.chat_session_id,
            status=i.status,
            tags=i.tags,
            created_at=i.created_at.isoformat(),
        )
        for i in insights
    ]


@router.get("/count")
async def get_insights_count(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Get insights count by status."""
    result = await db.execute(
        select(KnowledgeInsight.status, select(KnowledgeInsight.id).count()).group_by(
            KnowledgeInsight.status
        )
    )
    counts = {row[0]: row[1] for row in result.all()}

    return {
        "pending": counts.get("pending", 0),
        "approved": counts.get("approved", 0),
        "rejected": counts.get("rejected", 0),
        "total": sum(counts.values()),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_insight(
    insight_data: InsightCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Create a new insight (admin only)."""
    db_insight = KnowledgeInsight(
        title=insight_data.title,
        content=insight_data.content,
        source_type=insight_data.source_type,
        source_user_id=current_user.id,
        status="pending",  # Auto-approve for admin created
        tags=insight_data.tags,
    )
    db.add(db_insight)
    await db.commit()
    await db.refresh(db_insight)

    return InsightResponse(
        id=db_insight.id,
        title=db_insight.title,
        content=db_insight.content,
        source_type=db_insight.source_type,
        source_user_id=db_insight.source_user_id,
        chat_session_id=db_insight.chat_session_id,
        status=db_insight.status,
        tags=db_insight.tags,
        created_at=db_insight.created_at.isoformat(),
    )


@router.post("/{insight_id}/approve")
async def approve_insight(
    insight_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Approve an insight and add to Wiki (admin only)."""
    result = await db.execute(
        select(KnowledgeInsight).where(KnowledgeInsight.id == insight_id)
    )
    insight = result.scalar_one_or_none()

    if not insight:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Insight not found"
        )

    # Update status
    insight.status = "approved"
    insight.reviewed_by_id = current_user.id
    insight.reviewed_at = datetime.utcnow()

    await db.commit()

    return {"message": "Insight approved", "status": "approved"}


@router.post("/{insight_id}/reject")
async def reject_insight(
    insight_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Reject an insight (admin only)."""
    result = await db.execute(
        select(KnowledgeInsight).where(KnowledgeInsight.id == insight_id)
    )
    insight = result.scalar_one_or_none()

    if not insight:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Insight not found"
        )

    insight.status = "rejected"
    insight.reviewed_by_id = current_user.id
    insight.reviewed_at = datetime.utcnow()

    await db.commit()

    return {"message": "Insight rejected", "status": "rejected"}


@router.get("/context/{insight_id}")
async def get_insight_context(
    insight_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Get insight with chat context."""
    from backend.models.wiki import ChatMessage

    result = await db.execute(
        select(KnowledgeInsight).where(KnowledgeInsight.id == insight_id)
    )
    insight = result.scalar_one_or_none()

    if not insight:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Insight not found"
        )

    # Get chat context if available
    messages = []
    if insight.chat_session_id:
        chat_result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == insight.chat_session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(10)
        )
        chat_messages = chat_result.scalars().all()
        messages = [
            {
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat(),
            }
            for m in reversed(chat_messages)
        ]

    return {
        "insight": InsightResponse(
            id=insight.id,
            title=insight.title,
            content=insight.content,
            source_type=insight.source_type,
            source_user_id=insight.source_user_id,
            chat_session_id=insight.chat_session_id,
            status=insight.status,
            tags=insight.tags,
            created_at=insight.created_at.isoformat(),
        ),
        "chat_context": messages,
    }


from datetime import datetime
