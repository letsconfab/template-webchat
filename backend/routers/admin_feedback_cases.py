"""PII-safe administrative Feedback Case replay."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.dependencies.auth import get_current_admin_user
from backend.models.diagnostics import ExecutionTrace
from backend.models.feedback_case import FeedbackCase
from backend.models.user import User
from backend.models.wiki import ChatMessage
from backend.services.redaction import get_projection, mask_email


router = APIRouter(prefix="/api/admin/feedback-cases", tags=["admin-feedback-cases"])


async def _case_for_admin(db: AsyncSession, public_id: str) -> FeedbackCase:
    result = await db.execute(
        select(FeedbackCase)
        .options(
            selectinload(FeedbackCase.feedback),
            selectinload(FeedbackCase.owner),
            selectinload(FeedbackCase.chat_session),
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
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(
        select(FeedbackCase)
        .options(
            selectinload(FeedbackCase.feedback),
            selectinload(FeedbackCase.owner),
            selectinload(FeedbackCase.chat_session),
        )
        .order_by(FeedbackCase.created_at.desc(), FeedbackCase.id.desc())
        .limit(limit)
    )
    cases = [
        case
        for case in result.scalars().unique()
        if case.chat_session.ownership_state == "owned"
    ]
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
        "next_cursor": page[-1].id if has_more else None,
    }
