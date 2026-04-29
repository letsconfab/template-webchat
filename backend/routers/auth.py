"""Authentication router for user login, registration, and token management."""
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from backend.database import get_db
from backend.dependencies.auth import get_current_active_user
from backend.models.user import User
from backend.schemas.user import UserCreate, AdminCreate, UserLogin, UserResponse, Token
from backend.services.auth import (
    create_access_token,
    get_password_hash,
    verify_password
)
from backend.config import config

router = APIRouter(prefix="/api/auth", tags=["authentication"])


@router.post("/register", response_model=UserResponse)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Register a new user."""
    try:
        print("REGISTER CALLED:", user_data.email)

        # Check if user already exists
        result = await db.execute(select(User).where(User.email == user_data.email))
        existing_user = result.scalar_one_or_none()

        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Import invite model
        from backend.models.invite import Invite

        # 🔥 FIX: use "pending" string (matches DB)
        invite_result = await db.execute(
            select(Invite).where(
                and_(
                    Invite.email == user_data.email,
                    Invite.status == "pending",
                    Invite.expiry_date > datetime.utcnow()
                )
            )
        )
        invite = invite_result.scalar_one_or_none()

        print("INVITE FOUND:", invite)

        if not invite:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid invite found"
            )

        # Determine role from invite
        user_role = invite.role if invite else "user"

        # Hash password
        hashed_password = get_password_hash(user_data.password)

        # Create user
        db_user = User(
            email=user_data.email,
            password_hash=hashed_password,
            role=user_role,
            is_active=True
        )

        db.add(db_user)

        # Mark invite as used
        invite.status = "accepted"
        invite.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(db_user)

        return db_user

    except HTTPException:
        raise
    except Exception as e:
        print("REGISTER ERROR:", str(e))
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )


@router.post("/admin/register", response_model=UserResponse)
async def admin_register(
    admin_data: AdminCreate,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Register a new admin user."""
    if admin_data.password != admin_data.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match"
        )

    result = await db.execute(select(User).where(User.email == admin_data.email))
    existing_admin = result.scalar_one_or_none()

    if existing_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    hashed_password = get_password_hash(admin_data.password)

    db_admin = User(
        email=admin_data.email,
        password_hash=hashed_password,
        role="admin",
        is_active=True
    )

    db.add(db_admin)
    await db.commit()
    await db.refresh(db_admin)

    return db_admin


@router.post("/login", response_model=Token)
async def login(
    user_credentials: UserLogin,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Authenticate user and return access token."""
    result = await db.execute(select(User).where(User.email == user_credentials.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(user_credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )

    access_token_expires = timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """Get current user info."""
    return current_user


@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """Logout user."""
    return {"message": "Successfully logged out"}