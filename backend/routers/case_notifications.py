"""Administrative retry surface for durable case notifications."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies.auth import get_current_admin_user
from backend.models.user import User
from backend.services.case_notifications import case_notification_service
from backend.services.features import require_feature


router = APIRouter(
    prefix="/api/admin/case-notifications",
    tags=["case-notifications"],
)


def notification_response(notification) -> dict[str, Any]:
    return {
        "id": notification.id,
        "state": notification.state,
        "attempt_count": notification.attempt_count,
        "safe_error_category": notification.safe_error_category,
        "last_attempt_at": (
            notification.last_attempt_at.isoformat()
            if notification.last_attempt_at
            else None
        ),
        "sent_at": notification.sent_at.isoformat() if notification.sent_at else None,
    }


@router.post("/{notification_id}/retry")
async def retry_case_notification(
    notification_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await require_feature(db, "tester_email_notifications_enabled")
    try:
        notification = await case_notification_service.attempt(db, notification_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Notification not found")
    return notification_response(notification)
