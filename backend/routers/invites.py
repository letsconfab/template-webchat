"""Invite management router for user invitation system."""
from datetime import datetime, timedelta
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload

from database import get_db
from middleware.auth import get_admin_user, get_current_active_user
from models.user import User
from models.invite import Invite, InviteStatus
from schemas.invite import InviteCreate, InviteResponse, InviteAccept, InviteListResponse
from services.auth import generate_secure_token
from services.email import email_service

router = APIRouter(prefix="/api", tags=["invites"])


@router.post("/admin/invite-user", response_model=InviteResponse)
async def create_invite(
    invite_data: InviteCreate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Create and send user invitation (admin only)."""
    # Check if user already exists
    result = await db.execute(select(User).where(User.email == invite_data.email))
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists"
        )
    
    # Check for existing pending invite
    result = await db.execute(
        select(Invite).where(
            and_(
                Invite.email == invite_data.email,
                Invite.status == InviteStatus.PENDING,
                Invite.expiry_date > datetime.utcnow()
            )
        )
    )
    existing_invite = result.scalar_one_or_none()
    
    if existing_invite:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pending invitation already exists for this email"
        )
    
    # Generate unique token
    token = generate_secure_token()
    
    # Create invite
    db_invite = Invite(
        email=invite_data.email,
        token=token,
        status=InviteStatus.PENDING,
        expiry_date=datetime.utcnow() + timedelta(days=7),  # 7 days expiry
        created_by_id=current_user.id
    )
    
    db.add(db_invite)
    await db.commit()
    await db.refresh(db_invite)
    
    # Send invitation email
    email_sent = await email_service.send_invite_email(
        to_email=invite_data.email,
        invite_token=token,
        inviter_name=current_user.email
    )
    
    if not email_sent:
        # Mark invite as failed if email couldn't be sent
        db_invite.status = InviteStatus.CANCELLED
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send invitation email"
        )
    
    return db_invite


@router.get("/admin/invites", response_model=InviteListResponse)
async def get_invites(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: str = Query(None),
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Get all invites (admin only)."""
    query = select(Invite).options(selectinload(Invite.created_by))
    
    if status:
        query = query.where(Invite.status == status)
    
    query = query.offset(skip).limit(limit).order_by(Invite.created_at.desc())
    
    result = await db.execute(query)
    invites = result.scalars().all()
    
    return {"invites": invites, "total": len(invites)}


@router.get("/accept-invite/{token}")
async def check_invite_token(
    token: str,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Check if invite token is valid."""
    result = await db.execute(
        select(Invite).where(
            and_(
                Invite.token == token,
                Invite.status == InviteStatus.PENDING
            )
        )
    )
    invite = result.scalar_one_or_none()
    
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired invitation"
        )
    
    if invite.is_expired:
        # Mark as expired
        invite.status = InviteStatus.EXPIRED
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has expired"
        )
    
    return {
        "valid": True,
        "email": invite.email,
        "expiry_date": invite.expiry_date
    }


@router.post("/accept-invite/{token}")
async def accept_invite(
    token: str,
    accept_data: InviteAccept,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Accept invitation and create user account."""
    # Find and validate invite
    result = await db.execute(
        select(Invite).where(
            and_(
                Invite.token == token,
                Invite.status == InviteStatus.PENDING
            )
        )
    )
    invite = result.scalar_one_or_none()
    
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired invitation"
        )
    
    if invite.is_expired:
        # Mark as expired
        invite.status = InviteStatus.EXPIRED
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has expired"
        )
    
    # Check if token matches
    if token != accept_data.token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid token"
        )
    
    # Check if user already exists
    result = await db.execute(select(User).where(User.email == invite.email))
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        # Mark invite as accepted
        invite.status = InviteStatus.ACCEPTED
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists"
        )
    
    # Create new user
    from ..services.auth import get_password_hash
    hashed_password = get_password_hash(accept_data.password)
    
    db_user = User(
        email=invite.email,
        password_hash=hashed_password,
        role="user",
        is_active=True
    )
    
    db.add(db_user)
    
    # Mark invite as accepted
    invite.status = InviteStatus.ACCEPTED
    
    await db.commit()
    await db.refresh(db_user)
    
    # Send welcome email
    await email_service.send_welcome_email(
        to_email=db_user.email,
        user_name=db_user.email
    )
    
    # Send notification to admin who created the invite
    if invite.created_by:
        await email_service.send_invite_accepted_notification(
            admin_email=invite.created_by.email,
            user_email=db_user.email
        )
    
    return {
        "message": "Account created successfully",
        "user": {
            "id": db_user.id,
            "email": db_user.email,
            "role": db_user.role
        }
    }


@router.delete("/admin/invites/{invite_id}")
async def cancel_invite(
    invite_id: int,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Cancel invitation (admin only)."""
    result = await db.execute(select(Invite).where(Invite.id == invite_id))
    invite = result.scalar_one_or_none()
    
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found"
        )
    
    if invite.status != InviteStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot cancel invitation that is not pending"
        )
    
    invite.status = InviteStatus.CANCELLED
    await db.commit()
    
    return {"message": "Invitation cancelled successfully"}
