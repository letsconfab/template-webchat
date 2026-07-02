"""PII-safe administrative Feedback Case replay."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.dependencies.auth import get_current_admin_user
from backend.models.diagnostics import ExecutionTrace
from backend.models.feedback_case import CaseNotification, CaseReply, FeedbackCase
from backend.models.user import User
from backend.models.wiki import ChatMessage
from backend.services.redaction import get_projection, mask_email
from backend.services.redaction import project_text
from backend.routers.feedback_cases import ReplyCreate
from backend.routers.case_notifications import notification_response
from backend.services.case_notifications import case_notification_service
from backend.services.features import require_feature
from backend.services.features import admin_replay_readiness


router = APIRouter(prefix="/api/admin/feedback-cases", tags=["admin-feedback-cases"])


@router.get("/rollout/readiness")
async def get_replay_readiness(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int | bool]:
    return await admin_replay_readiness(db)


async def _case_for_admin(db: AsyncSession, public_id: str) -> FeedbackCase:
    result = await db.execute(
        select(FeedbackCase)
        .options(
            selectinload(FeedbackCase.feedback),
            selectinload(FeedbackCase.owner),
            selectinload(FeedbackCase.chat_session),
            selectinload(FeedbackCase.replies).selectinload(CaseReply.notification),
        )
        .where(FeedbackCase.public_id == public_id)
    )
    case = result.scalar_one_or_none()
    if case is None or case.chat_session.ownership_state != "owned":
        raise HTTPException(status_code=404, detail="Feedback Case not found")
    return case


@router.get("")
async def list_admin_feedback_cases(
    limit: int = Query(50, ge=1, le=100),
    case_status: str | None = Query(None, alias="status"),
    category: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    email: str | None = None,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await require_feature(db, "admin_replay_enabled")
    query = (
        select(FeedbackCase)
        .options(
            selectinload(FeedbackCase.feedback),
            selectinload(FeedbackCase.owner),
            selectinload(FeedbackCase.chat_session),
        )
        .order_by(FeedbackCase.created_at.desc(), FeedbackCase.id.desc())
    )
    if case_status:
        query = query.where(FeedbackCase.status == case_status)
    if date_from:
        query = query.where(FeedbackCase.created_at >= date_from)
    if date_to:
        query = query.where(FeedbackCase.created_at <= date_to)
    result = await db.execute(query.limit(limit * 5))
    cases = [
        case
        for case in result.scalars().unique()
        if case.chat_session.ownership_state == "owned"
        and (category is None or category in (case.feedback.categories or []))
        and (
            email is None
            or email.lower() in mask_email(case.owner.email).lower()
        )
    ][:limit]
    items = []
    for case in cases:
        comment = await get_projection(
            db,
            content_type="feedback",
            content_id=case.feedback_id,
            source_field="message",
        )
        items.append(
            {
                "case_id": case.public_id,
                "status": case.status,
                "categories": case.feedback.categories or [],
                "comment": comment.text,
                "comment_redaction_status": comment.status,
                "account_email": mask_email(case.owner.email),
                "created_at": case.created_at.isoformat(),
            }
        )
    return {"cases": items}


@router.get("/{case_id}/replay")
async def replay_feedback_case(
    case_id: str,
    cursor: int | None = None,
    limit: int = Query(100, ge=1, le=100),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await require_feature(db, "admin_replay_enabled")
    case = await _case_for_admin(db, case_id)
    rated = await db.get(ChatMessage, case.rated_message_id)
    if rated is None:
        raise HTTPException(status_code=404, detail="Feedback Case not found")

    query = (
        select(ChatMessage)
        .where(ChatMessage.chat_session_id == case.chat_session_id)
        .order_by(ChatMessage.created_at, ChatMessage.id)
        .limit(limit + 1)
    )
    if cursor is not None:
        cursor_message = await db.get(ChatMessage, cursor)
        if (
            cursor_message is None
            or cursor_message.chat_session_id != case.chat_session_id
        ):
            raise HTTPException(status_code=404, detail="Replay cursor not found")
        query = query.where(
            or_(
                ChatMessage.created_at > cursor_message.created_at,
                and_(
                    ChatMessage.created_at == cursor_message.created_at,
                    ChatMessage.id > cursor_message.id,
                ),
            )
        )
    result = await db.execute(query)
    rows = list(result.scalars())
    has_more = len(rows) > limit
    page = rows[:limit]

    trace_result = await db.execute(
        select(ExecutionTrace).where(
            ExecutionTrace.chat_message_id.in_([row.id for row in page])
        )
    )
    traces = {trace.chat_message_id: trace for trace in trace_result.scalars()}
    messages = []
    for row in page:
        projection = await get_projection(
            db,
            content_type="chat_message",
            content_id=row.id,
            source_field="content",
        )
        trace = traces.get(row.id)
        trace_payload = None
        if row.role == "assistant":
            trace_payload = (
                {
                    "status": trace.status,
                    "version": trace.version,
                    "events": trace.events,
                    "event_count": trace.event_count,
                    "byte_size": trace.byte_size,
                    "truncated": trace.truncated,
                }
                if trace
                else {"status": "not_captured"}
            )
        messages.append(
            {
                "id": row.id,
                "role": row.role,
                "content": projection.text,
                "redaction_status": projection.status,
                "created_at": row.created_at.isoformat(),
                "is_rated": row.id == rated.id,
                "is_post_feedback": (row.created_at, row.id)
                > (rated.created_at, rated.id),
                "execution_trace": trace_payload,
            }
        )

    comment = await get_projection(
        db,
        content_type="feedback",
        content_id=case.feedback_id,
        source_field="message",
    )
    correspondence = []
    for reply in case.replies:
        projection = await get_projection(
            db,
            content_type="case_reply",
            content_id=reply.id,
            source_field="raw_text",
        )
        correspondence.append(
            {
                "id": reply.id,
                "author_role": reply.author_role,
                "text": (
                    reply.raw_text
                    if reply.author_role == "admin"
                    else projection.text
                ),
                "redaction_status": (
                    "succeeded"
                    if reply.author_role == "admin"
                    else projection.status
                ),
                "created_at": reply.created_at.isoformat(),
                "notification": (
                    notification_response(reply.notification)
                    if reply.notification
                    else None
                ),
            }
        )
    return {
        "case": {
            "case_id": case.public_id,
            "status": case.status,
            "categories": case.feedback.categories or [],
            "comment": comment.text,
            "comment_redaction_status": comment.status,
            "account_email": mask_email(case.owner.email),
        },
        "messages": messages,
        "replies": correspondence,
        "next_cursor": page[-1].id if has_more else None,
    }


@router.post("/{case_id}/replies", status_code=status.HTTP_201_CREATED)
async def reply_to_case_as_admin(
    case_id: str,
    reply_data: ReplyCreate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await require_feature(db, "admin_replay_enabled")
    await require_feature(db, "tester_correspondence_enabled")
    result = await db.execute(
        select(FeedbackCase)
        .where(FeedbackCase.public_id == case_id)
        .with_for_update()
    )
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail="Feedback Case not found")
    reply = CaseReply(
        case_id=case.id,
        author_id=current_user.id,
        author_role="admin",
        raw_text=reply_data.text,
    )
    db.add(reply)
    await db.flush()
    await project_text(
        db,
        content_type="case_reply",
        content_id=reply.id,
        source_field="raw_text",
        raw_text=reply.raw_text,
    )
    case.status = "awaiting_user"
    notification = CaseNotification(
        case_reply_id=reply.id,
        recipient_user_id=case.user_id,
        state="pending",
    )
    db.add(notification)
    await db.commit()
    await db.refresh(notification)
    try:
        notification = await case_notification_service.attempt(db, notification.id)
    except Exception:
        # The committed pending row is the recovery point for an interrupted
        # process or unexpected delivery-worker failure.
        pass
    return {
        "id": reply.id,
        "status": case.status,
        "created_at": reply.created_at.isoformat(),
        "notification": notification_response(notification),
    }


@router.post("/{case_id}/resolve")
async def resolve_feedback_case(
    case_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    await require_feature(db, "admin_replay_enabled")
    await require_feature(db, "tester_correspondence_enabled")
    result = await db.execute(
        select(FeedbackCase)
        .where(FeedbackCase.public_id == case_id)
        .with_for_update()
    )
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail="Feedback Case not found")
    case.status = "resolved"
    await db.commit()
    return {"status": case.status}
