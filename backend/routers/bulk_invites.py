"""Admin API for bulk invite CSV upload, status, and cancel."""

from __future__ import annotations

from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.middleware.auth import get_admin_user
from backend.models.bulk_invite import InviteBatch
from backend.models.user import User, UserRole
from backend.schemas.bulk_invite import (
    BulkInviteBatchResponse,
    BulkInviteConfirmResponse,
    BulkInvitePreviewResponse,
)
from backend.services.bulk_invites import (
    BulkInviteError,
    cancel_batch,
    enqueue_batch,
    preview_csv,
    refresh_batch_counts,
)

router = APIRouter(prefix="/api/admin/bulk-invites", tags=["bulk-invites"])


def _role_value(role: str) -> str:
    if role in (UserRole.ADMIN.value, UserRole.USER.value):
        return role
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="role must be 'user' or 'admin'",
    )


@router.post("/preview", response_model=BulkInvitePreviewResponse)
async def preview_bulk_invite(
    file: UploadFile = File(...),
    role: str = Form("user"),
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    del current_user  # auth only
    role_value = _role_value(role)
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV upload only",
        )
    content = await file.read()
    try:
        result = await preview_csv(
            db,
            content=content,
            filename=file.filename,
            role=role_value,
        )
    except BulkInviteError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return result.as_dict()


@router.post(
    "/confirm",
    response_model=BulkInviteConfirmResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def confirm_bulk_invite(
    file: UploadFile = File(...),
    role: str = Form("user"),
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Enqueue a batch. Never sends inline — the invite worker drains the queue."""
    role_value = _role_value(role)
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV upload only",
        )
    content = await file.read()
    try:
        batch = await enqueue_batch(
            db,
            content=content,
            filename=file.filename,
            role=role_value,
            created_by_id=current_user.id,
        )
        await db.commit()
        await db.refresh(batch)
    except BulkInviteError as exc:
        await db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return {
        "batch_id": batch.id,
        "state": batch.state,
        "total_count": batch.total_count,
        "pending_count": batch.pending_count,
        "skipped_count": batch.skipped_count,
    }


@router.get("/{batch_id}", response_model=BulkInviteBatchResponse)
async def get_bulk_invite_batch(
    batch_id: int,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    del current_user
    batch = (
        await db.execute(
            select(InviteBatch)
            .options(selectinload(InviteBatch.recipients))
            .where(InviteBatch.id == batch_id)
        )
    ).scalar_one_or_none()
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    await refresh_batch_counts(db, batch.id)
    await db.commit()
    await db.refresh(batch)
    payload = BulkInviteBatchResponse.model_validate(batch)
    if batch.unknown_delivery_count:
        payload.cancel_note = (
            "Some recipients are unknown_delivery — delivery may or may not "
            "have occurred; they are never auto-retried and need an operator decision."
        )
    elif batch.state == "cancelled":
        payload.cancel_note = (
            "Cancellation applies to unclaimed recipients only. Addresses already "
            "in sending may still be delivered; SMTP cannot be retracted."
        )
    return payload


@router.get("", response_model=list[BulkInviteBatchResponse])
async def list_bulk_invite_batches(
    limit: int = 20,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    del current_user
    result = await db.execute(
        select(InviteBatch)
        .order_by(InviteBatch.created_at.desc())
        .limit(min(limit, 100))
    )
    batches = result.scalars().all()
    return [
        BulkInviteBatchResponse.model_validate(b).model_copy(
            update={"recipients": []}
        )
        for b in batches
    ]


@router.post("/{batch_id}/cancel", response_model=BulkInviteBatchResponse)
async def cancel_bulk_invite_batch(
    batch_id: int,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    del current_user
    try:
        batch = await cancel_batch(db, batch_id)
    except BulkInviteError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    loaded = (
        await db.execute(
            select(InviteBatch)
            .options(selectinload(InviteBatch.recipients))
            .where(InviteBatch.id == batch.id)
        )
    ).scalar_one()
    payload = BulkInviteBatchResponse.model_validate(loaded)
    payload.cancel_note = (
        "Cancellation applies to unclaimed recipients only. Addresses already "
        "in sending may still be delivered; SMTP cannot be retracted."
    )
    return payload
