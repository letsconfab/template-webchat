"""Invite management router for user invitation system."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.middleware.auth import get_admin_user
from backend.models.user import User
from backend.models.invite import Invite, InviteStatus
from backend.schemas.invite import (
    InviteCreate,
    InviteResponse,
    InviteAccept,
    InviteListResponse,
)
from backend.services.email import email_service
from backend.services.invites import (
    InviteClaimError,
    canonicalize_email,
    claim_invite,
    reap_expired_invites,
)

router = APIRouter(prefix="/api", tags=["invites"])


@router.post("/admin/invite-user", response_model=InviteResponse)
async def create_invite(
    invite_data: InviteCreate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Create and send user invitation (admin only)."""
    role = (
        invite_data.role.value
        if hasattr(invite_data.role, "value")
        else invite_data.role
    )
    try:
        db_invite = await claim_invite(
            db,
            email=str(invite_data.email),
            role=role,
            created_by_id=current_user.id,
        )
    except InviteClaimError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.detail,
        ) from exc

    await db.commit()
    await db.refresh(db_invite)

    # Send invitation email
    email_sent = await email_service.send_invite_email(
        to_email=db_invite.email,
        invite_token=db_invite.token,
        inviter_name=current_user.email,
        db=db,
    )

    if not email_sent:
        # Mark invite as failed if email couldn't be sent
        db_invite.status = InviteStatus.CANCELLED
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send invitation email",
        )

    return db_invite


@router.get("/admin/invites", response_model=InviteListResponse)
async def get_invites(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: str = Query(None),
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Get all invites (admin only).

    ``total`` is COUNT(*) over the same status filter as the page.
    ``accepted`` / ``pending`` are global status counts after the reaper.
    """
    await reap_expired_invites(db)
    await db.commit()

    filters = []
    if status:
        filters.append(Invite.status == status)

    count_q = select(func.count(Invite.id))
    if filters:
        count_q = count_q.where(*filters)
    total = await db.scalar(count_q) or 0

    accepted = (
        await db.scalar(
            select(func.count(Invite.id)).where(Invite.status == InviteStatus.ACCEPTED)
        )
        or 0
    )
    pending = (
        await db.scalar(
            select(func.count(Invite.id)).where(Invite.status == InviteStatus.PENDING)
        )
        or 0
    )

    query = select(Invite).options(selectinload(Invite.created_by))
    if filters:
        query = query.where(*filters)
    query = query.offset(skip).limit(limit).order_by(Invite.created_at.desc())

    result = await db.execute(query)
    invites = result.scalars().all()

    return {
        "items": invites,
        "total": total,
        "skip": skip,
        "limit": limit,
        "accepted": accepted,
        "pending": pending,
    }


@router.get("/check-invite/{email}")
async def check_invite_by_email(email: str, db: AsyncSession = Depends(get_db)) -> Any:
    """Check if email has a pending invite or already registered."""
    canonical = canonicalize_email(email)
    await reap_expired_invites(db)
    await db.commit()

    result = await db.execute(
        select(User).where(User.email_canonical == canonical)
    )
    existing_user = result.scalar_one_or_none()

    if existing_user:
        return {
            "has_invite": False,
            "role": None,
            "message": "You already have an account. Please login instead.",
            "already_registered": True,
        }

    result = await db.execute(
        select(Invite).where(
            and_(
                Invite.email_canonical == canonical,
                Invite.status == InviteStatus.PENDING,
            )
        )
    )
    invite = result.scalar_one_or_none()

    if invite:
        return {
            "has_invite": True,
            "role": invite.role,
            "message": f"You've been invited to join as {invite.role}. Complete your registration below.",
            "already_registered": False,
        }
    return {
        "has_invite": False,
        "role": None,
        "message": None,
        "already_registered": False,
    }


@router.get("/accept-invite/{token}")
async def check_invite_token(token: str, db: AsyncSession = Depends(get_db)) -> Any:
    """Check if invite token is valid."""
    await reap_expired_invites(db)
    await db.commit()

    result = await db.execute(
        select(Invite).where(
            and_(Invite.token == token, Invite.status == InviteStatus.PENDING)
        )
    )
    invite = result.scalar_one_or_none()

    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired invitation",
        )

    if invite.is_expired:
        invite.status = InviteStatus.EXPIRED
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation has expired"
        )

    return {
        "valid": True,
        "email": invite.email,
        "role": invite.role,
        "expiry_date": invite.expiry_date,
    }


@router.post("/accept-invite/{token}")
async def accept_invite(
    token: str, accept_data: InviteAccept, db: AsyncSession = Depends(get_db)
) -> Any:
    """Accept invitation and create user account."""
    await reap_expired_invites(db)

    result = await db.execute(
        select(Invite)
        .options(selectinload(Invite.created_by))
        .where(and_(Invite.token == token, Invite.status == InviteStatus.PENDING))
    )
    invite = result.scalar_one_or_none()

    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired invitation",
        )

    if invite.is_expired:
        invite.status = InviteStatus.EXPIRED
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation has expired"
        )

    if token != accept_data.token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token"
        )

    result = await db.execute(
        select(User).where(User.email_canonical == invite.email_canonical)
    )
    existing_user = result.scalar_one_or_none()

    if existing_user:
        invite.status = InviteStatus.ACCEPTED
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists",
        )

    from backend.services.auth import get_password_hash

    hashed_password = get_password_hash(accept_data.password)

    db_user = User(
        email=invite.email,
        email_canonical=invite.email_canonical,
        password_hash=hashed_password,
        role=invite.role,
        is_active=True,
    )

    db.add(db_user)
    invite.status = InviteStatus.ACCEPTED

    await db.commit()
    await db.refresh(db_user)

    await email_service.send_welcome_email(
        to_email=db_user.email, user_name=db_user.email, db=db
    )

    if invite.created_by_id:
        admin_email = invite.created_by.email if invite.created_by else None
        if admin_email:
            await email_service.send_invite_accepted_notification(
                admin_email=admin_email, user_email=db_user.email, db=db
            )

    return {
        "message": "Account created successfully",
        "user": {"id": db_user.id, "email": db_user.email, "role": db_user.role},
    }


@router.delete("/admin/invites/{invite_id}")
async def cancel_invite(
    invite_id: int,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Cancel invitation (admin only)."""
    result = await db.execute(select(Invite).where(Invite.id == invite_id))
    invite = result.scalar_one_or_none()

    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found"
        )

    if invite.status != InviteStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot cancel invitation that is not pending",
        )

    invite.status = InviteStatus.CANCELLED
    await db.commit()

    return {"message": "Invitation cancelled successfully"}
