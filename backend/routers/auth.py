"""Authentication router for user login, registration, and token management."""
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from dependencies.auth import get_current_active_user
from models.user import User
from schemas.user import UserCreate, AdminCreate, UserLogin, UserResponse, Token
from services.auth import (
    create_access_token,
    get_password_hash,
    verify_password,
    generate_secure_token
)
from config import config

router = APIRouter(prefix="/api/auth", tags=["authentication"])


@router.post("/register", response_model=UserResponse)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Register a new user."""
    # Check if user already exists
    result = await db.execute(select(User).where(User.email == user_data.email))
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Check if there's a valid invite for this email
    from models.invite import Invite, InviteStatus
    from sqlalchemy import and_
    
    result = await db.execute(
        select(Invite).where(
            and_(
                Invite.email == user_data.email,
                Invite.status == InviteStatus.PENDING,
                Invite.expiry_date > datetime.utcnow()
            )
        )
    )
    invite = result.scalar_one_or_none()
    
    # Determine role - use role from request if provided, otherwise use invite role or default to general
    user_role = user_data.role if user_data.role else (invite.role if invite else "general")
    
    # Create new user
    hashed_password = get_password_hash(user_data.password)
    db_user = User(
        email=user_data.email,
        password_hash=hashed_password,
        role=user_role,
        is_active=True
    )
    
    db.add(db_user)
    
    # Mark invite as accepted if exists
    if invite:
        invite.status = InviteStatus.ACCEPTED
    
    await db.commit()
    await db.refresh(db_user)
    
    return db_user


@router.post("/admin/register", response_model=UserResponse)
async def admin_register(
    admin_data: AdminCreate,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Register a new user through admin flow (respects invite roles)."""
    # Check if passwords match
    if admin_data.password != admin_data.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match"
        )
    
    # Check if user already exists
    result = await db.execute(select(User).where(User.email == admin_data.email))
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Check if there's a valid invite for this email
    from models.invite import Invite, InviteStatus
    from sqlalchemy import and_
    
    result = await db.execute(
        select(Invite).where(
            and_(
                Invite.email == admin_data.email,
                Invite.status == InviteStatus.PENDING,
                Invite.expiry_date > datetime.utcnow()
            )
        )
    )
    invite = result.scalar_one_or_none()
    
    # Determine role - use invite role if exists, otherwise default to general
    user_role = invite.role if invite else "general"
    
    # Create new user
    hashed_password = get_password_hash(admin_data.password)
    db_user = User(
        email=admin_data.email,
        password_hash=hashed_password,
        role=user_role,
        is_active=True
    )
    
    db.add(db_user)
    
    # Mark invite as accepted if exists
    if invite:
        invite.status = InviteStatus.ACCEPTED
    
    await db.commit()
    await db.refresh(db_user)
    
    return db_user


@router.post("/login", response_model=Token)
async def login(
    user_credentials: UserLogin,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Authenticate user and return access token."""
    # Find user by email
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
    
    # Create access token
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
    """
    Get current user information.
    
    Returns the authenticated user's details including:
    - id
    - email  
    - role
    - is_active
    - is_admin (computed property)
    - created_at
    - updated_at
    """
    return current_user


@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """Logout user (client-side token removal)."""
    return {"message": "Successfully logged out"}
