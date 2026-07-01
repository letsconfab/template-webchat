"""Execution Trace sanitization and hard persistence bounds."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.diagnostics import ExecutionTrace


TRACE_VERSION = 1
MAX_TRACE_EVENTS = 100
MAX_TRACE_BYTES = 64 * 1024
MAX_SUMMARY_CHARS = 256
ALLOWED_EVENT_KEYS = {
    "sequence",
    "timestamp",
    "event_type",
    "tool_name",
    "duration_ms",
    "safe_error_category",
    "source_identifiers",
    "result_count",
    "summary",
}


def bound_trace_events(events: list[dict[str, Any]]) -> tuple[list[dict], bool, int]:
    bounded: list[dict] = []
    truncated = len(events) > MAX_TRACE_EVENTS
    for event in events[:MAX_TRACE_EVENTS]:
        safe = {key: event[key] for key in ALLOWED_EVENT_KEYS if key in event}
        if "summary" in safe:
            safe["summary"] = str(safe["summary"])[:MAX_SUMMARY_CHARS]
        if "source_identifiers" in safe:
            safe["source_identifiers"] = [
                str(value)[:200] for value in safe["source_identifiers"][:20]
            ]
        candidate = [*bounded, safe]
        size = len(
            json.dumps(candidate, separators=(",", ":"), ensure_ascii=False).encode()
        )
        if size > MAX_TRACE_BYTES:
            truncated = True
            break
        bounded.append(safe)
    byte_size = len(
        json.dumps(bounded, separators=(",", ":"), ensure_ascii=False).encode()
    )
    return bounded, truncated, byte_size


async def persist_trace(
    db: AsyncSession,
    *,
    chat_message_id: int,
    events: list[dict[str, Any]],
    capture_failed: bool = False,
) -> ExecutionTrace:
    bounded, truncated, byte_size = bound_trace_events(events)
    trace = ExecutionTrace(
        chat_message_id=chat_message_id,
        version=TRACE_VERSION,
        status="failed" if capture_failed else "succeeded",
        events=bounded,
        event_count=len(bounded),
        byte_size=byte_size,
        truncated=truncated,
        safe_error_category="capture_failed" if capture_failed else None,
    )
    db.add(trace)
    await db.flush()
    return trace

