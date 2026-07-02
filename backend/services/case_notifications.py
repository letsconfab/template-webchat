"""Durable, generic Feedback Case email notifications."""

from __future__ import annotations

from datetime import datetime
from email.message import EmailMessage
from urllib.parse import urljoin, urlparse

import aiosmtplib
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models.feedback_case import CaseNotification, CaseReply, FeedbackCase
from backend.models.settings import SystemSettings


async def smtp_transport(
    *,
    settings: SystemSettings,
    recipient: str,
    subject: str,
    body: str,
) -> None:
    message = EmailMessage()
    message["From"] = settings.from_email
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    await aiosmtplib.send(
        message,
        hostname=settings.smtp_server,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        start_tls=settings.use_tls,
        timeout=15,
    )


class CaseNotificationService:
    def __init__(self) -> None:
        self.transport = smtp_transport

    @staticmethod
    def _configured(settings: SystemSettings | None) -> bool:
        if (
            settings is None
            or not settings.email_notifications_enabled
            or not settings.tester_email_notifications_enabled
        ):
            return False
        return all(
            (
                settings.smtp_server,
                settings.smtp_port,
                settings.smtp_username,
                settings.smtp_password,
                settings.from_email,
                settings.frontend_url,
            )
        ) and urlparse(settings.frontend_url).scheme in {"http", "https"}

    async def attempt(
        self,
        db: AsyncSession,
        notification_id: int,
    ) -> CaseNotification:
        result = await db.execute(
            select(CaseNotification)
            .options(
                selectinload(CaseNotification.recipient),
                selectinload(CaseNotification.reply)
                .selectinload(CaseReply.case)
                .selectinload(FeedbackCase.owner),
            )
            .where(CaseNotification.id == notification_id)
            .with_for_update()
        )
        notification = result.scalar_one_or_none()
        if notification is None:
            raise LookupError("Notification not found")
        if notification.state == "sent":
            return notification

        settings = (
            await db.execute(select(SystemSettings).limit(1))
        ).scalar_one_or_none()
        notification.attempt_count += 1
        notification.last_attempt_at = datetime.utcnow()
        notification.state = "pending"
        notification.safe_error_category = None
        await db.commit()

        if not self._configured(settings):
            notification.state = "failed"
            notification.safe_error_category = "disabled_configuration"
            await db.commit()
            return notification

        app_name = settings.app_name or "WebChat"
        case_url = urljoin(
            settings.frontend_url.rstrip("/") + "/",
            f"feedback/{notification.reply.case.public_id}",
        )
        subject = f"{app_name}: an admin replied"
        body = (
            f"An admin replied to your feedback case in {app_name}.\n\n"
            f"Sign in to view the case: {case_url}\n"
        )
        try:
            await self.transport(
                settings=settings,
                recipient=notification.recipient.email,
                subject=subject,
                body=body,
            )
        except TimeoutError:
            notification.state = "failed"
            notification.safe_error_category = "timeout"
        except Exception:
            notification.state = "failed"
            notification.safe_error_category = "smtp_error"
        else:
            notification.state = "sent"
            notification.sent_at = datetime.utcnow()
            notification.safe_error_category = None
        await db.commit()
        return notification


case_notification_service = CaseNotificationService()
