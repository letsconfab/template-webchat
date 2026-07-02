"""One-off bulk invite sender.

Replicates the exact logic of POST /api/admin/invite-user (backend/routers/invites.py)
for a fixed list of emails, in-process, so behavior matches the admin dashboard:
duplicate-user check, pending-invite check, secure token, 7-day expiry, email send,
and CANCELLED status on send failure. Run from the deploy dir with the venv python.
"""

import asyncio
from datetime import datetime, timedelta

from sqlalchemy import select, and_

from backend.database import AsyncSessionLocal
from backend.models.user import User
from backend.models.invite import Invite, InviteStatus
from backend.services.auth import generate_secure_token
from backend.services.email import email_service

# Attribute invites to this admin (matches current_user in the endpoint).
INVITER_ID = 2
INVITER_EMAIL = "sidd.gupta@zylum.in"
ROLE = "user"  # "General User"

EMAILS = [
    "Lonnie.hirsch@icp.consulting",
    "michelle.destefano@icp.consulting",
]


async def invite_one(db, email: str) -> str:
    # Already a user?
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        return "SKIP (user exists)"

    # Pending invite already?
    result = await db.execute(
        select(Invite).where(
            and_(
                Invite.email == email,
                Invite.status == InviteStatus.PENDING,
                Invite.expiry_date > datetime.utcnow(),
            )
        )
    )
    if result.scalar_one_or_none():
        return "SKIP (pending invite exists)"

    token = generate_secure_token()
    db_invite = Invite(
        email=email,
        token=token,
        role=ROLE,
        status=InviteStatus.PENDING,
        expiry_date=datetime.utcnow() + timedelta(days=7),
        created_by_id=INVITER_ID,
    )
    db.add(db_invite)
    await db.commit()
    await db.refresh(db_invite)

    email_sent = await email_service.send_invite_email(
        to_email=email,
        invite_token=token,
        inviter_name=INVITER_EMAIL,
        db=db,
    )

    if not email_sent:
        db_invite.status = InviteStatus.CANCELLED
        await db.commit()
        return "FAIL (email not sent -> invite CANCELLED)"

    return f"SENT (invite id={db_invite.id})"


async def main():
    sent = skipped = failed = 0
    async with AsyncSessionLocal() as db:
        for email in EMAILS:
            try:
                outcome = await invite_one(db, email)
            except Exception as e:
                await db.rollback()
                outcome = f"ERROR ({type(e).__name__}: {e})"
            if outcome.startswith("SENT"):
                sent += 1
            elif outcome.startswith("SKIP"):
                skipped += 1
            else:
                failed += 1
            print(f"{email:45s} {outcome}", flush=True)
            await asyncio.sleep(1.5)  # be gentle on the relay
    print(f"\nSummary: {sent} sent, {skipped} skipped, {failed} failed, "
          f"{len(EMAILS)} total")


if __name__ == "__main__":
    asyncio.run(main())
