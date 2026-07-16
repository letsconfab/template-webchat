"""Bulk invite: CSV preview/enqueue, lease claims, and out-of-process worker."""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import re
import socket
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import Any, Callable, Awaitable, Optional
from urllib.parse import urlparse

import aiosmtplib
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.models.bulk_invite import (
    BulkInviteRecipient,
    InviteBatch,
    InviteBatchState,
    RecipientState,
)
from backend.models.invite import Invite, InviteStatus
from backend.models.settings import SystemSettings
from backend.models.user import User
from backend.services.invites import (
    InviteClaimError,
    canonicalize_email,
    claim_invite,
    reap_expired_invites,
)
from backend.services.settings_service import settings_service

logger = logging.getLogger(__name__)

MAX_BATCH_SIZE = 500
MIN_BATCH_SIZE = 1
MAX_ATTEMPTS = 3
LEASE_SECONDS = 90
SMTP_TIMEOUT_SECONDS = 15
DEFAULT_PACE_SECONDS = 1.5
WORKER_IDLE_SECONDS = 2.0

_EMAIL_SHAPE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ANGLE_EMAIL = re.compile(r"<([^<>@\s]+@[^<>@\s]+\.[^<>@\s]+)>")
_BARE_EMAIL = re.compile(r"[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+")

TERMINAL_RECIPIENT_STATES = frozenset(
    {
        RecipientState.SENT.value,
        RecipientState.FAILED.value,
        RecipientState.SKIPPED.value,
        RecipientState.CANCELLED.value,
        RecipientState.UNKNOWN_DELIVERY.value,
    }
)


class BulkInviteError(Exception):
    """Domain error for bulk invite API mapping."""

    def __init__(self, detail: str, status_code: int = 400) -> None:
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


@dataclass
class ParsedRow:
    line_number: int
    raw: str
    email: Optional[str] = None
    email_canonical: Optional[str] = None
    invalid_reason: Optional[str] = None


@dataclass
class PreviewResult:
    filename: str
    role: str
    total_rows: int
    will_invite: list[ParsedRow] = field(default_factory=list)
    already_registered: list[ParsedRow] = field(default_factory=list)
    pending_invite: list[ParsedRow] = field(default_factory=list)
    invalid_rows: list[ParsedRow] = field(default_factory=list)
    duplicate_rows: list[ParsedRow] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "role": self.role,
            "total_rows": self.total_rows,
            "will_invite": len(self.will_invite),
            "already_registered": len(self.already_registered),
            "pending_invite": len(self.pending_invite),
            "invalid": len(self.invalid_rows),
            "duplicate_rows": len(self.duplicate_rows),
            "invalid_rows": [
                {
                    "line_number": row.line_number,
                    "raw": row.raw,
                    "reason": row.invalid_reason or "invalid",
                }
                for row in self.invalid_rows
            ],
            "sample_will_invite": [
                row.email for row in self.will_invite[:20] if row.email
            ],
        }


def extract_email(cell: str) -> Optional[str]:
    """Strip Name <email> wrappers and return a bare address, or None."""
    text = (cell or "").strip().strip('"').strip("'")
    if not text:
        return None
    angled = _ANGLE_EMAIL.search(text)
    if angled:
        return angled.group(1).strip()
    if _EMAIL_SHAPE.match(text):
        return text
    bare = _BARE_EMAIL.search(text)
    if bare and _EMAIL_SHAPE.match(bare.group(0)):
        return bare.group(0)
    return None


def _row_looks_like_header(cells: list[str]) -> bool:
    for cell in cells:
        if extract_email(cell):
            return False
    return True


def _email_column_index(header: list[str]) -> int:
    for idx, name in enumerate(header):
        if name.strip().lower() in {"email", "e-mail", "email address", "mail"}:
            return idx
    for idx, name in enumerate(header):
        if "email" in name.strip().lower():
            return idx
    raise BulkInviteError("CSV header has no email column")


def parse_csv_bytes(content: bytes) -> list[ParsedRow]:
    """Parse CSV upload into line-numbered rows with extracted emails."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise BulkInviteError("CSV must be UTF-8 encoded") from exc

    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise BulkInviteError("CSV is empty")

    first = [c.strip() for c in rows[0]]
    has_header = _row_looks_like_header(first)
    data_start = 1 if has_header else 0

    if has_header:
        email_idx = _email_column_index(first)
    else:
        email_idx = 0
        for idx, cell in enumerate(first):
            if extract_email(cell):
                email_idx = idx
                break

    parsed: list[ParsedRow] = []
    for offset, cells in enumerate(rows[data_start:]):
        line_number = data_start + offset + 1  # 1-based file line
        if not cells or all(not (c or "").strip() for c in cells):
            continue
        raw = cells[email_idx] if email_idx < len(cells) else ""
        if not raw.strip() and len(cells) == 1:
            raw = cells[0]
        email = extract_email(raw)
        if not email:
            # try any cell
            for cell in cells:
                email = extract_email(cell)
                if email:
                    raw = cell
                    break
        if not email:
            parsed.append(
                ParsedRow(
                    line_number=line_number,
                    raw=raw or ",".join(cells),
                    invalid_reason="no email address found",
                )
            )
            continue
        if not _EMAIL_SHAPE.match(email):
            parsed.append(
                ParsedRow(
                    line_number=line_number,
                    raw=raw,
                    invalid_reason="malformed email",
                )
            )
            continue
        parsed.append(
            ParsedRow(
                line_number=line_number,
                raw=raw,
                email=email.strip(),
                email_canonical=canonicalize_email(email),
            )
        )
    if not parsed:
        raise BulkInviteError("CSV contains no data rows")
    if len(parsed) > MAX_BATCH_SIZE:
        raise BulkInviteError(
            f"Batch exceeds server cap of {MAX_BATCH_SIZE} rows"
        )
    if len(parsed) < MIN_BATCH_SIZE:
        raise BulkInviteError("Batch is empty after parsing")
    return parsed


async def email_config_ready(db: AsyncSession) -> bool:
    """True only when SMTP settings are present (email.py alone is not enough)."""
    config = await settings_service.get_email_config(db)
    if not config:
        return False
    settings = await settings_service.get_settings(db)
    if settings is None:
        return False
    frontend = settings.frontend_url or config.get("frontend_url")
    if not frontend or urlparse(frontend).scheme not in {"http", "https"}:
        return False
    return True


async def preview_csv(
    db: AsyncSession,
    *,
    content: bytes,
    filename: str,
    role: str,
) -> PreviewResult:
    rows = parse_csv_bytes(content)
    await reap_expired_invites(db)

    seen: set[str] = set()
    result = PreviewResult(
        filename=filename or "upload.csv",
        role=role,
        total_rows=len(rows),
    )

    for row in rows:
        if row.invalid_reason or not row.email_canonical:
            result.invalid_rows.append(row)
            continue
        if row.email_canonical in seen:
            result.duplicate_rows.append(row)
            continue
        seen.add(row.email_canonical)

        user = (
            await db.execute(
                select(User).where(User.email_canonical == row.email_canonical)
            )
        ).scalar_one_or_none()
        if user:
            result.already_registered.append(row)
            continue

        live = (
            await db.execute(
                select(Invite).where(
                    Invite.email_canonical == row.email_canonical,
                    Invite.status == InviteStatus.PENDING,
                )
            )
        ).scalar_one_or_none()
        if live:
            result.pending_invite.append(row)
            continue

        result.will_invite.append(row)

    return result


async def enqueue_batch(
    db: AsyncSession,
    *,
    content: bytes,
    filename: str,
    role: str,
    created_by_id: int,
) -> InviteBatch:
    if not await email_config_ready(db):
        raise BulkInviteError(
            "Email is not configured; refuse to enqueue bulk invites",
            status_code=400,
        )

    preview = await preview_csv(
        db, content=content, filename=filename, role=role
    )
    if not preview.will_invite and not preview.already_registered and not preview.pending_invite:
        raise BulkInviteError("Nothing to enqueue from this CSV")

    now = datetime.utcnow()
    batch = InviteBatch(
        filename=preview.filename,
        role=role,
        created_by_id=created_by_id,
        state=InviteBatchState.QUEUED.value,
        created_at=now,
        updated_at=now,
    )
    db.add(batch)
    await db.flush()

    pending = 0
    skipped = 0
    for row in preview.will_invite:
        db.add(
            BulkInviteRecipient(
                batch_id=batch.id,
                email=row.email or "",
                email_canonical=row.email_canonical or "",
                line_number=row.line_number,
                state=RecipientState.PENDING.value,
            )
        )
        pending += 1
    for row in preview.already_registered + preview.pending_invite:
        db.add(
            BulkInviteRecipient(
                batch_id=batch.id,
                email=row.email or "",
                email_canonical=row.email_canonical or "",
                line_number=row.line_number,
                state=RecipientState.SKIPPED.value,
                safe_error_category=(
                    "already_registered"
                    if row in preview.already_registered
                    else "pending_invite"
                ),
            )
        )
        skipped += 1

    batch.total_count = pending + skipped
    batch.pending_count = pending
    batch.skipped_count = skipped
    await db.flush()
    return batch


async def cancel_batch(db: AsyncSession, batch_id: int) -> InviteBatch:
    """Mark parent + unclaimed recipients cancelled; return only after commit."""
    batch = (
        await db.execute(select(InviteBatch).where(InviteBatch.id == batch_id))
    ).scalar_one_or_none()
    if batch is None:
        raise BulkInviteError("Batch not found", status_code=404)
    if batch.state == InviteBatchState.CANCELLED.value:
        return batch
    if batch.state == InviteBatchState.COMPLETED.value:
        raise BulkInviteError("Completed batch cannot be cancelled")

    now = datetime.utcnow()
    result = await db.execute(
        update(BulkInviteRecipient)
        .where(
            BulkInviteRecipient.batch_id == batch_id,
            BulkInviteRecipient.state.in_(
                [
                    RecipientState.PENDING.value,
                    RecipientState.RETRY_WAIT.value,
                ]
            ),
        )
        .values(
            state=RecipientState.CANCELLED.value,
            lease_owner=None,
            lease_expires_at=None,
            next_attempt_at=None,
            updated_at=now,
        )
    )
    cancelled = result.rowcount or 0
    batch.state = InviteBatchState.CANCELLED.value
    batch.cancelled_count = (batch.cancelled_count or 0) + cancelled
    batch.pending_count = 0
    batch.retry_wait_count = 0
    batch.updated_at = now
    await db.commit()
    await db.refresh(batch)
    await refresh_batch_counts(db, batch.id)
    await db.commit()
    await db.refresh(batch)
    return batch


async def refresh_batch_counts(db: AsyncSession, batch_id: int) -> InviteBatch:
    batch = (
        await db.execute(select(InviteBatch).where(InviteBatch.id == batch_id))
    ).scalar_one()
    rows = (
        await db.execute(
            select(BulkInviteRecipient.state, func.count(BulkInviteRecipient.id))
            .where(BulkInviteRecipient.batch_id == batch_id)
            .group_by(BulkInviteRecipient.state)
        )
    ).all()
    counts = {state: n for state, n in rows}

    batch.pending_count = counts.get(RecipientState.PENDING.value, 0)
    batch.sent_count = counts.get(RecipientState.SENT.value, 0)
    batch.failed_count = counts.get(RecipientState.FAILED.value, 0)
    batch.skipped_count = counts.get(RecipientState.SKIPPED.value, 0)
    batch.cancelled_count = counts.get(RecipientState.CANCELLED.value, 0)
    batch.unknown_delivery_count = counts.get(
        RecipientState.UNKNOWN_DELIVERY.value, 0
    )
    batch.retry_wait_count = counts.get(RecipientState.RETRY_WAIT.value, 0)
    sending = counts.get(RecipientState.SENDING.value, 0)
    batch.total_count = sum(counts.values())
    batch.updated_at = datetime.utcnow()

    active = (
        batch.pending_count
        + batch.retry_wait_count
        + sending
    )
    if batch.state == InviteBatchState.CANCELLED.value:
        pass
    elif active == 0:
        batch.state = InviteBatchState.COMPLETED.value
    elif batch.state == InviteBatchState.QUEUED.value and (
        batch.sent_count
        or batch.failed_count
        or sending
        or batch.unknown_delivery_count
        or batch.retry_wait_count
    ):
        batch.state = InviteBatchState.PROCESSING.value

    await db.flush()
    return batch


async def reap_expired_leases(db: AsyncSession) -> int:
    """Move lease-expired sending rows to unknown_delivery. Never auto-retry."""
    now = datetime.utcnow()
    result = await db.execute(
        update(BulkInviteRecipient)
        .where(
            BulkInviteRecipient.state == RecipientState.SENDING.value,
            BulkInviteRecipient.lease_expires_at.is_not(None),
            BulkInviteRecipient.lease_expires_at < now,
        )
        .values(
            state=RecipientState.UNKNOWN_DELIVERY.value,
            lease_owner=None,
            lease_expires_at=None,
            safe_error_category="lease_expired",
            updated_at=now,
        )
    )
    return result.rowcount or 0


async def promote_retries(db: AsyncSession) -> int:
    now = datetime.utcnow()
    result = await db.execute(
        update(BulkInviteRecipient)
        .where(
            BulkInviteRecipient.state == RecipientState.RETRY_WAIT.value,
            BulkInviteRecipient.next_attempt_at.is_not(None),
            BulkInviteRecipient.next_attempt_at <= now,
        )
        .values(
            state=RecipientState.PENDING.value,
            next_attempt_at=None,
            updated_at=now,
        )
    )
    return result.rowcount or 0


async def claim_recipient(
    db: AsyncSession,
    *,
    recipient_id: int,
    worker_id: str,
    lease_seconds: int = LEASE_SECONDS,
) -> bool:
    """Portable conditional lease. Commit before SMTP; returns True if won."""
    now = datetime.utcnow()
    expires = now + timedelta(seconds=lease_seconds)
    result = await db.execute(
        update(BulkInviteRecipient)
        .where(
            BulkInviteRecipient.id == recipient_id,
            BulkInviteRecipient.state == RecipientState.PENDING.value,
        )
        .values(
            state=RecipientState.SENDING.value,
            lease_owner=worker_id,
            lease_expires_at=expires,
            attempt_count=BulkInviteRecipient.attempt_count + 1,
            updated_at=now,
        )
    )
    await db.commit()
    return (result.rowcount or 0) == 1


def _is_retryable_smtp_error(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError, socket.timeout)):
        return True
    if isinstance(exc, (ConnectionError, OSError, aiosmtplib.SMTPConnectError)):
        return True
    if isinstance(exc, aiosmtplib.SMTPException):
        code = getattr(exc, "code", None)
        if code == 550:
            return False
        # connection / transient
        if code is not None and 400 <= int(code) < 500:
            return True
        msg = str(exc).lower()
        if "550" in msg:
            return False
        if "timeout" in msg or "connect" in msg:
            return True
    msg = str(exc).lower()
    if "550" in msg:
        return False
    if "timeout" in msg or "connection" in msg:
        return True
    return False


async def smtp_invite_transport(
    *,
    settings: SystemSettings,
    recipient: str,
    subject: str,
    html_body: str,
) -> None:
    message = EmailMessage()
    message["From"] = settings.from_email
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content("Please view this invitation in an HTML-capable client.")
    message.add_alternative(html_body, subtype="html")
    await aiosmtplib.send(
        message,
        hostname=settings.smtp_server,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        start_tls=settings.use_tls,
        timeout=SMTP_TIMEOUT_SECONDS,
    )


def _invite_email_html(
    *,
    app_name: str,
    app_description: str,
    invite_link: str,
    inviter_name: Optional[str],
) -> str:
    byline = f" by {inviter_name}" if inviter_name else ""
    return f"""<!DOCTYPE html>
<html><body style="font-family: Arial, sans-serif; color: #333;">
<p>Hello,</p>
<p>You've been invited to join {app_name}{byline}!</p>
<p>{app_name} is {app_description}</p>
<p><a href="{invite_link}">Accept Invitation</a></p>
<p>Or copy this link: {invite_link}</p>
<p>This invitation will expire in 7 days.</p>
</body></html>"""


class BulkInviteWorker:
    """Exactly one global consumer per process; paces sends globally."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        worker_id: Optional[str] = None,
        pace_seconds: float = DEFAULT_PACE_SECONDS,
        transport: Optional[
            Callable[..., Awaitable[None]]
        ] = None,
        fail_success_commit: bool = False,
    ) -> None:
        self.session_factory = session_factory
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:12]}"
        self.pace_seconds = pace_seconds
        self.transport = transport or smtp_invite_transport
        # Test hook: simulate process death after SMTP accept, before SENT commit.
        self.fail_success_commit = fail_success_commit
        self._started = False
        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task] = None

    def start_once(self) -> bool:
        """Process-local guard. Returns False if already started."""
        if self._started:
            return False
        self._started = True
        self._stop.clear()
        self._task = asyncio.create_task(self._run_loop(), name="bulk-invite-worker")
        return True

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task

    async def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                worked = await self.process_one()
            except Exception:
                logger.exception("Bulk invite worker cycle failed")
                worked = False
            if self._stop.is_set():
                break
            await asyncio.sleep(
                self.pace_seconds if worked else WORKER_IDLE_SECONDS
            )

    async def process_one(self) -> bool:
        """Reap, promote retries, claim one recipient, send, commit terminal state."""
        async with self.session_factory() as db:
            reaped = await reap_expired_leases(db)
            promoted = await promote_retries(db)
            if reaped or promoted:
                await db.commit()
                # Refresh counts for affected batches (best-effort)
                if reaped:
                    batch_ids = (
                        await db.execute(
                            select(BulkInviteRecipient.batch_id)
                            .where(
                                BulkInviteRecipient.state
                                == RecipientState.UNKNOWN_DELIVERY.value,
                                BulkInviteRecipient.safe_error_category
                                == "lease_expired",
                            )
                            .distinct()
                        )
                    ).scalars().all()
                    for bid in batch_ids:
                        await refresh_batch_counts(db, bid)
                    await db.commit()

            candidate = await self._next_claimable(db)
            if candidate is None:
                return False
            recipient_id, batch_id = candidate.id, candidate.batch_id

        # Claim in its own transaction (commit before SMTP).
        async with self.session_factory() as db:
            won = await claim_recipient(
                db, recipient_id=recipient_id, worker_id=self.worker_id
            )
            if not won:
                return False

        await self._deliver(recipient_id, batch_id)
        return True

    async def _next_claimable(
        self, db: AsyncSession
    ) -> Optional[BulkInviteRecipient]:
        result = await db.execute(
            select(BulkInviteRecipient)
            .join(InviteBatch, InviteBatch.id == BulkInviteRecipient.batch_id)
            .where(
                BulkInviteRecipient.state == RecipientState.PENDING.value,
                InviteBatch.state.in_(
                    [
                        InviteBatchState.QUEUED.value,
                        InviteBatchState.PROCESSING.value,
                    ]
                ),
            )
            .order_by(BulkInviteRecipient.id.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _deliver(self, recipient_id: int, batch_id: int) -> None:
        async with self.session_factory() as db:
            batch = (
                await db.execute(
                    select(InviteBatch).where(InviteBatch.id == batch_id)
                )
            ).scalar_one_or_none()
            recipient = (
                await db.execute(
                    select(BulkInviteRecipient).where(
                        BulkInviteRecipient.id == recipient_id
                    )
                )
            ).scalar_one_or_none()
            if recipient is None or recipient.state != RecipientState.SENDING.value:
                return

            if batch is None or batch.state == InviteBatchState.CANCELLED.value:
                # Parent cancelled after claim — leave as sending until lease
                # expires into unknown_delivery, or mark cancelled only if we
                # never contacted SMTP. Spec: already sending may still deliver.
                # We still attempt delivery for in-flight claims.
                pass

            if batch and batch.state == InviteBatchState.QUEUED.value:
                batch.state = InviteBatchState.PROCESSING.value
                await db.flush()

            settings = (
                await db.execute(select(SystemSettings).limit(1))
            ).scalar_one_or_none()
            if not await email_config_ready(db) or settings is None:
                await self._finish_failed(
                    db,
                    recipient,
                    category="disabled_configuration",
                    retryable=False,
                )
                await refresh_batch_counts(db, batch_id)
                await db.commit()
                return

            # Ensure invite exists (reuse on retry).
            try:
                invite = await self._ensure_invite(db, recipient, batch)
            except InviteClaimError as exc:
                category = (
                    "already_registered"
                    if "already exists" in exc.detail.lower()
                    else "pending_invite"
                )
                recipient.state = RecipientState.SKIPPED.value
                recipient.safe_error_category = category
                recipient.lease_owner = None
                recipient.lease_expires_at = None
                recipient.updated_at = datetime.utcnow()
                await refresh_batch_counts(db, batch_id)
                await db.commit()
                return

            await db.commit()

            # SMTP outside any open transaction.
            inviter = (
                await db.execute(select(User).where(User.id == batch.created_by_id))
            ).scalar_one_or_none() if batch else None
            app_name = settings.app_name or "WebChat"
            app_description = (
                settings.app_description or "an AI-powered chat platform"
            )
            frontend = (settings.frontend_url or "").rstrip("/")
            invite_link = f"{frontend}/register?token={invite.token}"
            subject = f"You're invited to join {app_name}"
            html = _invite_email_html(
                app_name=app_name,
                app_description=app_description,
                invite_link=invite_link,
                inviter_name=inviter.email if inviter else None,
            )

            try:
                await self.transport(
                    settings=settings,
                    recipient=recipient.email,
                    subject=subject,
                    html_body=html,
                )
            except Exception as exc:
                logger.warning(
                    "Bulk invite SMTP failed for recipient %s: %s",
                    recipient_id,
                    exc,
                )
                async with self.session_factory() as db2:
                    rec = (
                        await db2.execute(
                            select(BulkInviteRecipient).where(
                                BulkInviteRecipient.id == recipient_id
                            )
                        )
                    ).scalar_one()
                    retryable = _is_retryable_smtp_error(exc)
                    await self._finish_failed(
                        db2,
                        rec,
                        category="smtp_error" if retryable else "hard_reject",
                        retryable=retryable,
                    )
                    await refresh_batch_counts(db2, batch_id)
                    await db2.commit()
                return

            # Commit success in a fresh session so a commit failure after
            # transport leaves the row in sending → reaper → unknown_delivery.
            async with self.session_factory() as db3:
                rec = (
                    await db3.execute(
                        select(BulkInviteRecipient).where(
                            BulkInviteRecipient.id == recipient_id
                        )
                    )
                ).scalar_one()
                now = datetime.utcnow()
                rec.state = RecipientState.SENT.value
                rec.sent_at = now
                rec.lease_owner = None
                rec.lease_expires_at = None
                rec.safe_error_category = None
                rec.updated_at = now
                await refresh_batch_counts(db3, batch_id)
                if self.fail_success_commit:
                    await db3.rollback()
                    raise RuntimeError("simulated commit failure after transport")
                await db3.commit()

    async def _ensure_invite(
        self,
        db: AsyncSession,
        recipient: BulkInviteRecipient,
        batch: Optional[InviteBatch],
    ) -> Invite:
        if recipient.invite_id:
            invite = (
                await db.execute(
                    select(Invite).where(Invite.id == recipient.invite_id)
                )
            ).scalar_one_or_none()
            if invite is not None:
                return invite

        if batch is None:
            raise InviteClaimError("Batch missing")

        invite = await claim_invite(
            db,
            email=recipient.email,
            role=batch.role,
            created_by_id=batch.created_by_id,
        )
        recipient.invite_id = invite.id
        await db.flush()
        return invite

    async def _finish_failed(
        self,
        db: AsyncSession,
        recipient: BulkInviteRecipient,
        *,
        category: str,
        retryable: bool,
    ) -> None:
        now = datetime.utcnow()
        recipient.lease_owner = None
        recipient.lease_expires_at = None
        recipient.safe_error_category = category
        recipient.updated_at = now
        if (
            retryable
            and recipient.attempt_count < MAX_ATTEMPTS
            and category != "hard_reject"
        ):
            delay = 2 ** recipient.attempt_count
            recipient.state = RecipientState.RETRY_WAIT.value
            recipient.next_attempt_at = now + timedelta(seconds=delay)
        else:
            recipient.state = RecipientState.FAILED.value
            recipient.next_attempt_at = None
        await db.flush()


# Module-level worker for the systemd entrypoint (one process, one consumer).
_worker: Optional[BulkInviteWorker] = None


def get_worker(
    session_factory: async_sessionmaker[AsyncSession],
    **kwargs: Any,
) -> BulkInviteWorker:
    global _worker
    if _worker is None:
        _worker = BulkInviteWorker(session_factory, **kwargs)
    return _worker
