"""Chat Session management API — list, create, rename, delete."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies.auth import get_current_active_user
from backend.models.chat import ChatSession
from backend.models.user import User
from backend.models.wiki import ChatMessage

router = APIRouter(prefix="/api/chat-sessions", tags=["chat-sessions"])


class ChatSessionOut(BaseModel):
    id: int
    client_uuid: str
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatSessionUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


def _serialize(session: ChatSession) -> ChatSessionOut:
    return ChatSessionOut(
        id=session.id,
        client_uuid=session.client_uuid,
        title=session.title or "New chat",
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


async def _owned_session(
    db: AsyncSession,
    user: User,
    client_uuid: str,
) -> ChatSession:
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.client_uuid == client_uuid,
            ChatSession.user_id == user.id,
            ChatSession.ownership_state == "owned",
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Chat Session not found")
    return session


@router.get("", response_model=list[ChatSessionOut])
async def list_sessions(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession)
        .where(
            ChatSession.user_id == current_user.id,
            ChatSession.ownership_state == "owned",
        )
        .order_by(desc(ChatSession.updated_at), desc(ChatSession.id))
    )
    return [_serialize(s) for s in result.scalars().all()]


@router.post("", response_model=ChatSessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    session = ChatSession(
        client_uuid=str(uuid4()),
        user_id=current_user.id,
        ownership_state="owned",
        title="New chat",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return _serialize(session)


@router.get("/{client_uuid}", response_model=ChatSessionOut)
async def get_session(
    client_uuid: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _owned_session(db, current_user, client_uuid)
    return _serialize(session)


@router.patch("/{client_uuid}", response_model=ChatSessionOut)
async def rename_session(
    client_uuid: str,
    body: ChatSessionUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _owned_session(db, current_user, client_uuid)
    session.title = body.title.strip() or "New chat"
    session.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(session)
    return _serialize(session)


@router.delete("/{client_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    client_uuid: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _owned_session(db, current_user, client_uuid)
    # Messages cascade via ORM / FK; delete explicitly for SQLite test setups.
    await db.execute(
        delete(ChatMessage).where(ChatMessage.chat_session_id == session.id)
    )
    await db.delete(session)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
