"""User management router for admin operations."""
from datetime import datetime, timedelta
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, case, delete, or_, select, func, update

from backend.database import get_db
from backend.middleware.auth import get_admin_user
from backend.models.user import User, UserRole
from backend.models.invite import Invite, InviteStatus
from backend.models.chat import ChatSession
from backend.models.diagnostics import AdminProjection
from backend.models.feedback_case import CaseReply, FeedbackCase
from backend.models.wiki import ChatMessage, UserFeedback
from backend.schemas.user import UserListResponse, UserResponse, UserUpdate
from backend.services.invites import canonicalize_email

router = APIRouter(prefix="/api/admin", tags=["admin", "users"])

STALE_DAYS = 90
SortBy = Literal[
    "created_at",
    "email",
    "role",
    "is_active",
    "last_login_at",
    "inferred_last_activity_at",
    "last_seen_at",
]
SortOrder = Literal["asc", "desc"]
StatusFilter = Literal["active", "inactive"]


def _last_seen_expr():
    """SQL expression for max(last_login_at, inferred_last_activity_at)."""
    return case(
        (
            and_(
                User.last_login_at.isnot(None),
                User.inferred_last_activity_at.isnot(None),
            ),
            case(
                (
                    User.last_login_at >= User.inferred_last_activity_at,
                    User.last_login_at,
                ),
                else_=User.inferred_last_activity_at,
            ),
        ),
        (User.last_login_at.isnot(None), User.last_login_at),
        (User.inferred_last_activity_at.isnot(None), User.inferred_last_activity_at),
        else_=None,
    )


def _apply_user_filters(
    query,
    *,
    status_filter: Optional[StatusFilter],
    stale: Optional[bool],
):
    if status_filter == "active":
        query = query.where(User.is_active.is_(True))
    elif status_filter == "inactive":
        query = query.where(User.is_active.is_(False))

    if stale is not None:
        last_seen = _last_seen_expr()
        cutoff = datetime.utcnow() - timedelta(days=STALE_DAYS)
        # Unknown (both NULL) is never stale. Inclusive boundary: last_seen <= cutoff.
        if stale:
            query = query.where(last_seen.isnot(None), last_seen <= cutoff)
        else:
            query = query.where(or_(last_seen.is_(None), last_seen > cutoff))

    return query


@router.get("/users", response_model=UserListResponse)
async def get_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    sort_by: SortBy = Query("created_at"),
    sort_order: SortOrder = Query("desc"),
    status_filter: Optional[StatusFilter] = Query(None, alias="status"),
    stale: Optional[bool] = Query(None),
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Get users with pagination, sorting, and status/stale filters (admin only)."""
    sort_map = {
        "created_at": User.created_at,
        "email": User.email,
        "role": User.role,
        "is_active": User.is_active,
        "last_login_at": User.last_login_at,
        "inferred_last_activity_at": User.inferred_last_activity_at,
        "last_seen_at": _last_seen_expr(),
    }
    order_col = sort_map[sort_by]
    order_expr = order_col.asc() if sort_order == "asc" else order_col.desc()

    base = _apply_user_filters(select(User), status_filter=status_filter, stale=stale)
    count_q = _apply_user_filters(
        select(func.count(User.id)), status_filter=status_filter, stale=stale
    )
    total = await db.scalar(count_q) or 0

    result = await db.execute(base.order_by(order_expr).offset(skip).limit(limit))
    users = result.scalars().all()
    return {"items": users, "total": total, "skip": skip, "limit": limit}


@router.get("/users/stats")
async def get_user_stats(
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Get user statistics (admin only).

    ``regular_users`` and ``admin_users`` count only *active* accounts so
    inactive users are not misclassified as regular.
    """
    total_users = await db.scalar(select(func.count(User.id))) or 0
    active_users = (
        await db.scalar(select(func.count(User.id)).where(User.is_active.is_(True)))
        or 0
    )
    admin_users = (
        await db.scalar(
            select(func.count(User.id)).where(
                User.role == UserRole.ADMIN,
                User.is_active.is_(True),
            )
        )
        or 0
    )
    regular_users = (
        await db.scalar(
            select(func.count(User.id)).where(
                User.role == UserRole.USER,
                User.is_active.is_(True),
            )
        )
        or 0
    )

    return {
        "total_users": total_users,
        "active_users": active_users,
        "admin_users": admin_users,
        "regular_users": regular_users,
    }


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Get specific user by ID (admin only)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return user


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_update: UserUpdate,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Update user information (admin only).

    Guards and the mutation share one transaction. Active admins are locked
    with FOR UPDATE on Postgres; SQLite still runs the checks transactionally
    (FOR UPDATE is a no-op there).
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    update_data = user_update.model_dump(exclude_unset=True)
    if not update_data:
        return user

    # Lock active-admin rows for last-admin / demotion races.
    await db.execute(
        select(User.id)
        .where(User.role == UserRole.ADMIN, User.is_active.is_(True))
        .with_for_update()
        .order_by(User.id)
    )

    # Self-deactivate: only when is_active is explicitly False (not when unset).
    if user.id == current_user.id and user_update.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate yourself",
        )

    new_role = update_data.get("role")
    if new_role is not None and hasattr(new_role, "value"):
        new_role = new_role.value
        update_data["role"] = new_role

    will_deactivate = user_update.is_active is False and user.is_active
    will_demote = (
        new_role is not None
        and user.role == UserRole.ADMIN
        and new_role != UserRole.ADMIN
        and new_role != "admin"
    )

    # Last-active-admin: block any demotion/deactivation that would leave zero.
    # Runs under the lock above. Concurrent Postgres coverage is still needed;
    # SQLite ignores FOR UPDATE but remains transactional for sequential cases.
    if (will_deactivate or will_demote) and user.role == UserRole.ADMIN:
        active_admin_count = (
            await db.scalar(
                select(func.count(User.id)).where(
                    User.role == UserRole.ADMIN,
                    User.is_active.is_(True),
                )
            )
            or 0
        )
        if active_admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate or demote the last active admin",
            )

    # Self-demotion: block changing own role away from admin (when other admins remain).
    if (
        user.id == current_user.id
        and new_role is not None
        and user.role == UserRole.ADMIN
        and new_role != UserRole.ADMIN
        and new_role != "admin"
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot demote yourself from admin",
        )

    if "email" in update_data and update_data["email"] is not None:
        update_data["email"] = str(update_data["email"]).strip()
        update_data["email_canonical"] = canonicalize_email(update_data["email"])

    for field, value in update_data.items():
        setattr(user, field, value)

    # Hygiene: cancel pending invites for a deactivated address (canonical match).
    if will_deactivate:
        await db.execute(
            update(Invite)
            .where(
                Invite.email_canonical == user.email_canonical,
                Invite.status == InviteStatus.PENDING,
            )
            .values(status=InviteStatus.CANCELLED, updated_at=datetime.utcnow())
        )

    await db.commit()
    await db.refresh(user)

    return user


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Delete user (admin only). Kept for API compatibility; not exposed in the UI."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself",
        )

    # Existing feedback/message foreign keys predate database-level cascades.
    # Delete the user's owned diagnostic roots in dependency order; Feedback
    # Cases and Chat Messages cascade from these roots.
    message_ids = (
        select(ChatMessage.id)
        .join(ChatSession, ChatSession.id == ChatMessage.chat_session_id)
        .where(ChatSession.user_id == user.id)
    )
    feedback_ids = select(UserFeedback.id).where(UserFeedback.user_id == user.id)
    reply_ids = (
        select(CaseReply.id)
        .join(FeedbackCase, FeedbackCase.id == CaseReply.case_id)
        .where(FeedbackCase.user_id == user.id)
    )
    await db.execute(
        delete(AdminProjection).where(
            or_(
                and_(
                    AdminProjection.content_type == "chat_message",
                    AdminProjection.content_id.in_(message_ids),
                ),
                and_(
                    AdminProjection.content_type == "feedback",
                    AdminProjection.content_id.in_(feedback_ids),
                ),
                and_(
                    AdminProjection.content_type == "case_reply",
                    AdminProjection.content_id.in_(reply_ids),
                ),
            )
        )
    )
    await db.execute(delete(UserFeedback).where(UserFeedback.user_id == user.id))
    await db.execute(delete(ChatSession).where(ChatSession.user_id == user.id))
    await db.delete(user)
    await db.commit()

    return {"message": "User deleted successfully"}
