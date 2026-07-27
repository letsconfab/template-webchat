"""Administrator-curated starter journeys API."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies.auth import get_current_active_user, get_current_admin_user
from backend.models.journey import Journey
from backend.models.user import User

public_router = APIRouter(prefix="/api/journeys", tags=["journeys"])
admin_router = APIRouter(prefix="/api/admin/journeys", tags=["admin-journeys"])


class JourneyCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    purpose: str = Field(default="", max_length=500)
    starter_prompt: str = Field(min_length=1)
    icon: Optional[str] = Field(default=None, max_length=64)
    display_order: int = 0
    is_active: bool = True
    knowledge_source_labels: List[str] = Field(default_factory=list)


class JourneyUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=120)
    purpose: Optional[str] = Field(default=None, max_length=500)
    starter_prompt: Optional[str] = Field(default=None, min_length=1)
    icon: Optional[str] = Field(default=None, max_length=64)
    display_order: Optional[int] = None
    is_active: Optional[bool] = None
    knowledge_source_labels: Optional[List[str]] = None


class JourneyOut(BaseModel):
    id: int
    title: str
    purpose: str
    starter_prompt: str
    icon: Optional[str]
    display_order: int
    is_active: bool
    knowledge_source_labels: List[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


def _serialize(row: Journey) -> JourneyOut:
    labels = row.knowledge_source_labels or []
    if not isinstance(labels, list):
        labels = []
    return JourneyOut(
        id=row.id,
        title=row.title,
        purpose=row.purpose or "",
        starter_prompt=row.starter_prompt,
        icon=row.icon,
        display_order=row.display_order or 0,
        is_active=bool(row.is_active),
        knowledge_source_labels=[str(x) for x in labels],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@public_router.get("", response_model=list[JourneyOut])
async def list_active_journeys(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    _ = current_user
    result = await db.execute(
        select(Journey)
        .where(Journey.is_active.is_(True))
        .order_by(Journey.display_order, Journey.id)
    )
    return [_serialize(j) for j in result.scalars().all()]


@admin_router.get("", response_model=list[JourneyOut])
async def admin_list_journeys(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    _ = current_user
    result = await db.execute(
        select(Journey).order_by(Journey.display_order, Journey.id)
    )
    return [_serialize(j) for j in result.scalars().all()]


@admin_router.post("", response_model=JourneyOut, status_code=status.HTTP_201_CREATED)
async def admin_create_journey(
    body: JourneyCreate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    _ = current_user
    row = Journey(
        title=body.title.strip(),
        purpose=body.purpose.strip(),
        starter_prompt=body.starter_prompt.strip(),
        icon=body.icon,
        display_order=body.display_order,
        is_active=body.is_active,
        knowledge_source_labels=body.knowledge_source_labels,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _serialize(row)


@admin_router.patch("/{journey_id}", response_model=JourneyOut)
async def admin_update_journey(
    journey_id: int,
    body: JourneyUpdate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    _ = current_user
    result = await db.execute(select(Journey).where(Journey.id == journey_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Journey not found")

    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        if isinstance(value, str):
            value = value.strip()
        setattr(row, key, value)
    row.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(row)
    return _serialize(row)


@admin_router.delete("/{journey_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_journey(
    journey_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    _ = current_user
    result = await db.execute(select(Journey).where(Journey.id == journey_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Journey not found")
    await db.delete(row)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
