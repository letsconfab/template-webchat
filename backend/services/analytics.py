"""Admin usage analytics — volume buckets from timestamps."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Literal, Sequence

ALLOWED_DAYS = frozenset({7, 30, 90})


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def window_start(days: int, today: date | None = None) -> datetime:
    """Inclusive start of the UTC window (00:00 of the first day)."""
    if days not in ALLOWED_DAYS:
        raise ValueError(f"days must be one of {sorted(ALLOWED_DAYS)}")
    end = today or utc_today()
    start_day = end - timedelta(days=days - 1)
    return datetime(start_day.year, start_day.month, start_day.day)


def zero_fill_days(days: int, today: date | None = None) -> list[date]:
    end = today or utc_today()
    start = end - timedelta(days=days - 1)
    out: list[date] = []
    cursor = start
    while cursor <= end:
        out.append(cursor)
        cursor += timedelta(days=1)
    return out


def bucket_timestamps(
    timestamps: Iterable[datetime | None],
    days: int,
    today: date | None = None,
) -> tuple[dict[str, int], int]:
    """Bucket naive-UTC datetimes into YYYY-MM-DD counts; return (buckets, undated)."""
    if days not in ALLOWED_DAYS:
        raise ValueError(f"days must be one of {sorted(ALLOWED_DAYS)}")
    start = window_start(days, today)
    end_day = today or utc_today()
    end = datetime(end_day.year, end_day.month, end_day.day) + timedelta(days=1)

    counts: dict[str, int] = defaultdict(int)
    undated = 0
    for ts in timestamps:
        if ts is None:
            undated += 1
            continue
        # Treat naive as UTC; strip tz if present
        if ts.tzinfo is not None:
            ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
        if ts < start or ts >= end:
            continue
        key = ts.date().isoformat()
        counts[key] += 1
    return dict(counts), undated


def build_daily_series(
    message_counts: dict[str, int],
    session_counts: dict[str, int],
    days: int,
    today: date | None = None,
) -> list[dict]:
    end = today or utc_today()
    series = []
    for day in zero_fill_days(days, end):
        key = day.isoformat()
        series.append(
            {
                "date": key,
                "messages": message_counts.get(key, 0),
                "sessions": session_counts.get(key, 0),
                "is_partial": day == end,
            }
        )
    return series


def summarize_feedback(
    feedback_types: Sequence[str | None],
) -> dict[str, int]:
    thumbs_up = sum(1 for t in feedback_types if t == "thumbs_up")
    thumbs_down = sum(1 for t in feedback_types if t == "thumbs_down")
    return {"thumbs_up": thumbs_up, "thumbs_down": thumbs_down}
