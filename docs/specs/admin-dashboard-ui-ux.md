# Admin Dashboard UI and UX Changes

Status: Revised after adversarial review — approved for implementation
Design source: grilling interview, 16 July 2026
Review: Codex (`gpt-5.6-sol`) adversarial plan review, 16 July 2026 — 15
findings, 4 blockers, verdict "needs revision first". This revision accepts 14
findings and defers part of one. Revision history is at the end.

This plan covers five changes to the admin surface: repair of the design token
set, a usage analytics section, deactivation of stale users, invite integrity,
and bulk invitation by CSV. It is written to be executed as five sequential
pull requests.

## Findings that shaped this plan

The codebase investigation drove the design. These are the load-bearing facts.
Claims corrected by the adversarial review are marked.

**The design system does not work.** `frontend/src/index.css` defines seven CSS
variables. The shadcn components in `frontend/src/components/ui/` reference ten
that do not exist: `--destructive`, `--secondary`, `--accent`, `--card`,
`--ring`, `--input`, and their foreground pairs. Today `Button
variant="destructive"` renders with no background, `ghost` and `outline` hover
states do nothing, `Alert variant="destructive"` is indistinguishable from an
info alert, and `focus-visible:ring-ring` produces no visible focus ring
anywhere. This is why `AdminDashboard.tsx` hardcodes 200-character gradient
class strings instead of using the kit — the kit is broken, so it was bypassed.
The Tailwind config is at `frontend/tailwind.config.js`; there is no root
config.

**`<Toaster />` has never been mounted.** `AuthContext.tsx` calls `toast.error`
on every login failure and `toast.success` on login. None of it has ever
rendered. Login errors are silently swallowed.

**Bulk invite cannot loop the existing endpoint.** `POST /admin/invite-user`
sends SMTP inline, rebuilding the connection per send
(`backend/services/email.py:176`), with no timeout. `scripts/bulk_invite.py:94`
sleeps 1.5s between sends. Realistic throughput is ~3s per email, sequential. A
500-address batch is a 25-minute operation. No proxy will hold that request
open.

**A deploy will kill a running batch.** Production is a single uvicorn process
(`scripts/webchat.service:41`, no `--workers`) with `TimeoutStopSec=30` and
`Restart=always`. Every deploy runs `systemctl restart webchat`. A batch
interrupted at minute 12 gets 30 seconds, then SIGKILL — no unwind, no
`finally`, no commit — and systemd restarts immediately with no memory of who
was already emailed.

**The durable outbox pattern exists in this repo, and it is at-least-once, not
exactly-once.** `CaseNotification` (`backend/models/feedback_case.py:116-149`)
tracks an operation rather than a domain object.
`backend/services/case_notifications.py:89-131` increments `attempt_count`,
flushes, calls SMTP, and commits the terminal state **after** the send returns.
A process death between the relay accepting a message and the commit landing
leaves the row `pending`, so a resume re-sends it.

> **Corrected by review (finding 1).** The first draft claimed "resume cannot
> double-send". That is false. The window is real and this plan now designs for
> it explicitly rather than asserting it away.

The service also holds its row lock across the SMTP call, and its tests run
SQLite (`tests/test_case_notifications.py:42`), where SQLAlchemy silently drops
`FOR UPDATE`. The locking is therefore unproven by anything in the suite.

> **Corrected by review (finding 2).** `with_for_update()` cannot be copied as
> evidence of concurrency safety. This plan uses a portable conditional-update
> lease instead, and does not hold a transaction open during SMTP.

**The email service reports success without sending.**
`backend/services/email.py:66-77` returns `True` if the settings row is not
configured. A bulk run against a misconfigured environment would report "500
sent" with zero delivered.

**Do not copy the Drive sync.** `backend/services/drive_sync_service.py:194`
and `:255` make synchronous `googleapiclient` calls inside `async def` with no
`asyncio.to_thread`. On a single-worker uvicorn this stalls the entire event
loop, chat included. A latent production bug, not a precedent.

**No token or cost data exists.** Nothing records token counts or cost. Usage
analytics must be built from `ChatMessage.created_at` and
`ChatSession.created_at`. Both are nullable with no `server_default`, and the
existing stats endpoint silently excludes NULL rows via its predicate
(`backend/routers/feedback.py:329-331`).

**Hard delete is broken and would destroy the analytics.** `DELETE
/api/admin/users/{id}` cascades through `ChatSession` → `chat_messages` →
`execution_traces`, and `UserFeedback` → `feedback_cases` → `case_replies` —
the rows feeding the analytics in PR 2. It also throws `IntegrityError: NOT
NULL constraint failed: invites.created_by_id` for anyone who has created an
invite, verified by execution, so no admin can be hard-deleted. The two tests
touching it seed users with only chat sessions, which is why this was never
caught.

**There is no last-login field.** No `last_login`, `last_seen`, or
`last_active`. Login (`backend/routers/auth.py:137-165`) writes nothing back.
`updated_at` is `onupdate=datetime.utcnow`, so it moves only when an admin
edits the user — sorting by it ranks the most active users as the stalest.
Chat messages are written without touching their parent session
(`backend/main.py:293-324`), so `chat_sessions.updated_at` alone is not
activity; message activity must be joined through `chat_sessions`.

**`GET /api/admin/users/stats` has never executed.** Registered at
`users.py:157`, after `/users/{user_id}` at `:40`, so FastAPI matches the
parametrized route first and `user_id: int` fails to parse `"stats"`.

**The self-protection guard is inverted.** `users.py:77` reads `not
user_update.is_active` where `is_active: Optional[bool] = None`, so `not None`
is `True`. An admin editing their own email gets a bogus "Cannot deactivate
yourself". Conversely `PUT {"is_active": true, "role": "user"}` on yourself
passes the guard and self-demotes out of admin. `UserUpdate.role` is an
arbitrary string (`backend/schemas/user.py:36-40`), and user mutation is an
unlocked read-then-write (`users.py:67-89`), so two concurrent requests can
each see two admins and demote a different one, leaving zero.

**Email comparison is case-sensitive everywhere.** `users.email` is a plain
unique string (`backend/models/user.py:24-27`); invite checks compare exact
strings (`invites.py:38`, `:49-53`); login compares exact strings
(`auth.py:143-146`). Lowercasing only in the bulk path would not detect a
legacy mixed-case account and would not stop the single-invite endpoint
creating a differently-cased duplicate.

**`invites.email` is not unique** and expiry is lazily evaluated — a row stays
`pending` past `expiry_date` until something touches the token endpoint. Invite
creation is check-then-act (`invites.py:37-63` then `:65-80`), and a row lock
cannot lock the absence of a matching row.

**`role` is an unvalidated bare string.** `InviteCreate`
(`backend/schemas/invite.py:9-13`) types it `role: str = "user"` with no enum
constraint, and `accept_invite` copies `invite.role` onto the new `User` at
`invites.py:257`.

**Invite and user list contracts do not support pagination.** `GET
/api/admin/users` returns a bare list with fixed `created_at DESC` ordering and
no total (`users.py:22-37`). The invite list's `total` is `len()` of the
current page (`invites.py:102-121`). `AdminDashboard.tsx:349-392` computes
counts client-side over a `limit=100` fetch — upload 500 invites and it reports
"Total: 100".

**Deactivation does not close an open chat socket.** HTTP auth re-reads
`is_active` per request (`backend/middleware/auth.py:49-63`), but the
WebSocket checks once at handshake (`backend/main.py:681-696`) and the message
loop never rechecks (`:699-709`, `:751-786`). `ConnectionManager` tracks bare
sockets, not user IDs (`:275-290`).

**`/api/feedback/admin` is not orphaned.** It is part of the documented
production verification procedure (`DEPLOYMENT.md:263`, `:274`) and provides a
paginated, masked administrative feedback API not replaced by this work.

> **Corrected by review (finding 13).** The first draft deleted it, reasoning
> only from frontend callers. `/feedback/stats` is genuinely orphaned once
> `FeedbackDashboard.tsx` goes; `/feedback/admin` is not.

**Deactivated users cannot walk back in via an old invite.** `accept_invite`
(`invites.py:236-247`) finds any existing user by email, marks the invite
accepted, and raises `400 "User with this email already exists"`. It does not
create an account and does not reactivate one.

> **Corrected by review (finding 11).** The first draft asserted a
> reactivation security hole. It does not exist. Cancelling obsolete pending
> invites on deactivation is retained as policy hygiene, not as a security fix.

**Postgres in production, SQLite in tests.** `date_trunc` is Postgres-only.
Volumes are currently small, but nothing enforces that bound.

**Migrations run at boot.** `scripts/webchat.service:40-41` runs
`scripts/migrate.py upgrade` via `ExecStartPre`, and a failure returns nonzero
(`migrate.py:143-155`). The service does not start until migrations finish. No
`created_at` column in any table is indexed.

## Decisions

| Question | Decision |
|---|---|
| What "usage over time" means | Volume: messages and chat sessions per day. No cost or token analytics. |
| Analytics placement | Inline on the dashboard, filling the empty section at `AdminDashboard.tsx:331`. |
| Time range | Selector: 7 / 30 / 90 days, default 30, governing the whole section. Constrained to that literal set server-side. |
| Charting | Add `recharts` via the shadcn chart component. |
| Analytics API | One new endpoint returning tiles and buckets in one payload. Delete `/feedback/stats` only. |
| Bulk invite scale | 50–500 per batch. Asynchronous. |
| Delivery semantics | **At-least-once.** The duplicate window is documented, not denied. |
| Sender topology | **A separate systemd worker**, not an in-process task. |
| Interrupted batches | Auto-resume by the worker, plus a Cancel honoured between sends. |
| Bulk invite input | CSV upload only. No paste path. |
| Role in CSV | No role column. Single role chosen in the UI, enum-validated. |
| Before sending | Preview and confirm. |
| User administration placement | New `/admin/users` page. Dashboard keeps analytics and links out. |
| Delete vs deactivate | Deactivate only. `DELETE` stays unexposed. |
| Deactivation semantics | **Blocks new requests and new sockets.** Does not close an open socket. |
| Defining stale | `last_login_at` for true logins; `inferred_last_activity_at` for derived history. Never conflated. |
| Bulk deactivate | No. Single user at a time. |
| Fifth admin header | Build a shared `AdminLayout` and retrofit the existing four pages. |
| Delivery | Five sequential PRs. |

## PR 1 — Foundation

No new features, no migrations. Pure repair.

Repair the token set in `frontend/src/index.css`: add `--destructive`,
`--secondary`, `--accent`, `--card`, `--popover`, `--input`, `--ring` and their
foreground pairs, for both the light and `.dark` blocks, and map them in
`frontend/tailwind.config.js`. This fixes destructive and secondary buttons,
every ghost and outline hover state, destructive alerts, card backgrounds, and
focus rings across all admin pages at once.

Mount `<Toaster />` at the application root so the existing `toast` calls in
`AuthContext.tsx` render. Login failures become visible for the first time.

Build a minimal `AdminLayout` — title, back-to-dashboard, logout — and adopt it
in `AdminSettings`, `AdminFeedbackCasesPage`, `InsightsReview`, and
`GoogleDriveSettings`, deleting the four bespoke headers. Logout becomes
reachable from every admin page; it is currently missing from Settings and both
feedback pages.

Collapse the duplicate dashboard route. `/dashboard` and `/admin/dashboard`
render the same component (`App.tsx:94`, `:128`). Keep `/admin/dashboard`;
make `/dashboard` a `<Navigate to="/admin/dashboard" replace />` **inside the
existing protection**, so an unauthenticated hit still stores `returnTo` and
lands on login rather than bouncing through an unprotected redirect. Also fix
`ChatPage.tsx:354`, which links every user — including non-admins — to
`/dashboard`, an admin-only route; gate it on `isAdmin` like the
`/admin/settings` link four lines above it.

Regression tests are required here, not optional. Recent commits (`65a091e`,
`4e76121`, `ec14435`) and
`docs/field-debug/2026-07-14-feedback-returnto-chat-bounce.md` record a
hard-won `returnTo` and feature-flag ordering constraint. Cover: unauthenticated
`/dashboard`; session-stored `returnTo=/dashboard`; `/login?returnTo=/dashboard`;
admin and non-admin outcomes; and the existing `/feedback/:id` deep-link cases.

Fix the role-selection highlight at `AdminDashboard.tsx:554` and `:569`, which
interpolates `${...}` inside a plain quoted string rather than a template
literal, so the selected state has never rendered.

Delete dead code: `pages/FeedbackDashboard.tsx`,
`components/admin/InviteUser.tsx`, `components/auth/LoginForm.tsx`,
`components/auth/InviteAcceptForm.tsx`, `pages/KnowledgeBook.tsx`, and the
commented-out card blocks at `AdminDashboard.tsx:163-187` and `:306-328`.

Add component-level tests asserting each repaired variant and the focus ring
actually resolve to a value, so the token set cannot silently regress.

Read the `dataviz` and `frontend-design` skills before choosing token values.

## PR 2 — Analytics

Self-contained, no migration.

Add `GET /api/admin/analytics/overview?days=30`, admin-gated. `days` is
constrained server-side to the literal set `{7, 30, 90}` — not an open integer.
It returns, in one payload: thumbs-up and thumbs-down totals for the window,
and daily buckets of message count and session count.

Query semantics, all specified rather than implied:

- Select **only** the timestamp and type/role columns. The existing endpoint
  fetches whole ORM objects (`feedback.py:318-335`), and `ChatMessage` carries
  a `Text` body plus a JSON metadata blob (`wiki.py:128-132`) — materializing
  90 days of message bodies to count them would be gratuitous on a 4 GiB box.
- Bucket boundaries are UTC days. Stored timestamps are naive UTC.
- Today is a partial bucket and is labelled as such in the UI.
- Days with no activity are zero-filled, so the axis is continuous.
- "Messages" counts both user and assistant rows. The chart labels this.
- Rows with a NULL `created_at` cannot be bucketed. They are counted and
  reported as an explicit "undated" figure rather than silently dropped, which
  is what the current stats predicate does today.
- Bucket in Python after a windowed, column-projected fetch — one code path for
  Postgres and SQLite. Include a test at representative maximum volume asserting
  both row count and latency, so the "current volume is small" assumption is
  enforced rather than assumed.

Delete `GET /feedback/stats`. **Do not delete `GET /feedback/admin`** — it is a
documented deployment verification surface (`DEPLOYMENT.md:263`, `:274`) and a
paginated masked admin API this work does not replace. If it should go, that is
a separate deprecation with the deployment procedure updated first.

Add `recharts` and the shadcn chart component, which colours series through CSS
variables — the mechanism PR 1 repairs.

Fill the empty Analytics section at `AdminDashboard.tsx:331` with the thumbs
tiles, the volume chart, and the 7/30/90 selector, which governs the whole
section.

If volume later grows, add `ix_chat_messages_created_at` and
`ix_user_feedback_created_at` and push grouping into SQL. Not now.

## PR 3 — User management

**Migration `0008_last_login_at` adds columns only. No backfill runs in the
migration.** Migrations execute via `ExecStartPre` (`webchat.service:40-41`), so
an unbounded cross-table scan over three unindexed `created_at` columns would
block the service from starting, and a failure would keep it down until fixed by
hand. The schema change is additive and instant; the data population is a
separate, resumable, post-deploy job.

Two columns, never conflated:

- `last_login_at` — written only at a real login (`backend/routers/auth.py:160`).
  Means exactly what its name says.
- `inferred_last_activity_at` — populated by the backfill from recorded
  activity. Explicitly an inference.

Writing derived activity into a field called `last_login_at` would make the data
semantically false, so it is not done. The UI shows a single **Last seen**
column sourced from `max(last_login_at, inferred_last_activity_at)`, labelled
with which source produced it, so an admin can tell a measured login from an
inferred one.

Backfill as a resumable CLI following the established out-of-band pattern
(`scripts/backfill_feedback_cases.py`, `backend/services/feedback_backfill.py:18-33`):
batched, incrementally committed, re-runnable, driven by a Makefile target. It
computes, per user, the max of `chat_sessions.updated_at`,
`user_feedback.created_at`, and `chat_messages.created_at` **joined through
`chat_sessions`** — messages do not touch their parent session's `updated_at`
(`backend/main.py:293-324`), so session `updated_at` alone is not activity.

Stale is defined, not left to intuition:

- Threshold: no activity for **90 days**, inclusive boundary, evaluated in UTC.
- `NULL` on both columns means **unknown**, never stale. A user created but
  never active shows "Never seen" and is sorted separately.
- Until the backfill completes, unknown is the honest majority state. The UI
  says so rather than implying everyone is stale.

Build `/admin/users`, starting from `components/admin/UserList.tsx` — orphaned
but structurally sound. Note `UserResponse.is_admin` is a plain `@property` and
Pydantic v2 does not serialise it; derive from `role`.

Extend the list contract, which does not currently support what the UI needs
(`users.py:22-37` returns a bare list, fixed ordering, no total). Define a
paginated envelope: `items`, a true filtered `total` from a separate `COUNT(*)`
over the same predicate, `skip`, `limit`. Add allow-listed `sort_by` and
`sort_order`, plus status and stale-cutoff filters. Apply the same envelope to
the invite list, whose `total` is currently `len()` of the page
(`invites.py:102-121`), and define whether expired-but-still-pending rows count
as pending — they do not, once PR 4's reaper exists.

Reorder `GET /users/stats` above `/users/{user_id}` so it becomes reachable for
the first time. Its `regular_users` is `total - admin`, counting inactive users
as regular; fix while exposing it.

Correct the guards, all inside one transaction with the update:

- Predicate becomes `user_update.is_active is False`.
- `UserUpdate.role` becomes enum-validated — PR 5 tightening `InviteCreate.role`
  does not protect this editor.
- Self-demotion is blocked; nothing guards `role` today.
- A last-active-admin check counts only active admins and runs under a
  transaction-level lock over the active-admin rows. An unlocked read-then-write
  lets two concurrent requests each see two admins and demote a different one,
  leaving zero — with no in-app recovery, since `/admin/register` and invites
  both require admin. Concurrent Postgres tests required.

Cancel pending invites matching a deactivated address. This is hygiene — stale
invites should not outlive the decision to revoke access — not a security fix.

**Deactivation semantics are defined as: blocks new requests and new sockets.**
It takes effect on the very next HTTP request, because `is_active` is re-read
from the database per request rather than trusted from the token
(`middleware/auth.py:49-63`), and the WebSocket handshake rejects with 4403
(`main.py:687`). It does **not** close a socket that is already open: the
message loop never rechecks user status (`main.py:699-709`, `:751-786`) and
`ConnectionManager` tracks sockets without user IDs (`:275-290`). For dormant
users this is theoretical — they have no open socket. It is not theoretical for
"revoke this person right now", which this feature does not claim to do. See
Out of scope.

Do not expose `DELETE`.

## PR 4 — Invite integrity

Bulk invite cannot be made correct on the current invite path, so the path is
fixed first, in its own PR, where it can stabilise before a fan-out rides on it.

**The problem.** Invite creation checks for an account and a live invite, then
independently inserts (`invites.py:37-63` then `:65-80`). `invites.email` is
indexed, not unique (`models/invite.py:28-34`). A row lock cannot lock the
absence of a row. So bulk and single-invite — or bulk and a second bulk — can
both observe "no live invite" and both create and send one.

**Canonical email.** Add `email_canonical` to `invites` and `users`, populated
on write as the trimmed lowercase address. Every comparison — registration,
login, single invite, bulk invite, deactivation matching, acceptance — uses it.
Lowercasing only in the bulk path would miss a legacy mixed-case account and
would not stop the single-invite endpoint creating a differently-cased
duplicate.

Adding case-insensitive uniqueness to `users` can fail on existing data, so the
migration is preceded by an **audit script** that reports collisions. Collisions
are resolved by hand before the constraint lands. The migration refuses to
proceed rather than silently picking a winner.

**Expiry reaper.** Lazily-evaluated expiry means `status` stays `pending` past
`expiry_date`. A reaper flips expired pending rows to `EXPIRED`, run before any
uniqueness decision. This is also what makes a partial unique index viable, and
it independently fixes the over-reported Pending count.

**The claim invariant.** A unique partial index on `invites(email_canonical)
WHERE status = 'pending'` — supported by both Postgres and SQLite. One live
invitation per address, enforced by the database rather than by a check.

Route both the single-invite endpoint and bulk through **one**
`claim_invite(email, role)` service: canonicalize, reap expired, check for an
existing account, insert. The insert either succeeds or raises a uniqueness
violation, which is translated into "already invited". The decision and the
claim are one transaction. Check-then-act is gone.

Tighten `InviteCreate.role` to an enum. `role: "wizard"` is accepted today and
copied onto the created `User` at `invites.py:257`.

Move the invite Total / Accepted / Pending counts server-side using the PR 3
envelope. They are computed client-side over a `limit=100` fetch today and would
be visibly wrong the first time a 500-row CSV lands.

Add invite test coverage. There is none today — no `test_invites.py`, no
frontend test touching `AdminDashboard.tsx`.

## PR 5 — Bulk invite

Last, deliberately. The only piece that sends irreversible email to real
people.

### Delivery semantics

**At-least-once. This is stated plainly because it cannot be engineered away
here.** The relay is contacted, then the result is committed. A process death in
between leaves no durable record of a send that did happen. The plan therefore
does not claim exactly-once; it bounds and surfaces the window instead.

### Topology: a separate worker

The sender is a **separate systemd unit**, not a task inside the web process.
The API creates, previews, displays, and cancels batches; it never sends.

This follows the split the repo already uses for long work
(`scripts/backfill_feedback_cases.py`, `backend/services/feedback_backfill.py`),
and it buys four things an in-process driver cannot: the send does not share an
event loop with chat; it does not compete for 4 GiB with the in-process
`SentenceTransformer`; a web deploy does not touch it at all; and its unit gets
its own `TimeoutStopSec` generous enough to finish the send in flight and commit
the result, which directly narrows the finding-1 window rather than merely
documenting it.

Exactly one consumer, globally — not one task per batch. Per-batch pacing would
not bound the total rate: ten batches would fire ten sends per interval into one
relay. The worker holds a process-local `start_once()` guard and paces globally.

This requires a new unit in the deploy configuration. That is a real change to
`.tmt-agent-deploy/config.yaml` and `DEPLOYMENT.md`, and it is the largest
structural consequence of this revision.

### Schema — migration `0009_invite_batches`

A parent batch row: uploaded filename, role, requesting admin, state, counts.

One row per recipient, with an `invite_id` foreign key to the `Invite` that PR
4's `claim_invite` created. Without that link a retry cannot tell its own
pending invite from a competing one, and would either skip itself or mint a
second token. The recipient and its invite are persisted together.

Recipient states form a complete machine:

| State | Meaning |
|---|---|
| `pending` | Queued, unclaimed |
| `sending` | Claimed under a lease, SMTP in flight |
| `sent` | Relay accepted and the commit landed |
| `retry_wait` | Transient failure, eligible after backoff |
| `failed` | Terminal: non-retryable, or attempts exhausted |
| `skipped` | Deduped at send time: account exists, or a live invite exists |
| `cancelled` | Batch cancelled before this recipient was claimed |
| `unknown_delivery` | Lease expired while `sending`. **May or may not have been delivered.** |

Transitions: `pending → sending → {sent, retry_wait, failed}`; `retry_wait →
pending` after backoff; `pending → {skipped, cancelled}`; `sending →
unknown_delivery` only via the reaper.

Retry policy, which the first draft left undefined while carrying an
`attempt_count` that therefore meant nothing: maximum 3 attempts; exponential
backoff; timeouts and connection errors are retryable; a hard rejection (550,
invalid address) is terminal immediately.

`unknown_delivery` is the honest name for the finding-1 window. It is **never**
retried automatically — that is precisely the case where a retry may send a
second email to someone who already received one. It surfaces in the UI as
requiring an operator decision.

### Claiming — a portable lease, not `FOR UPDATE`

Claim with a conditional update:

```
UPDATE bulk_invite_recipients
   SET state = 'sending', lease_owner = :worker_id,
       lease_expires_at = :now + 90s, attempt_count = attempt_count + 1
 WHERE id = :id AND state = 'pending'
```

Commit, check the affected row count, and only send if this worker won. This is
atomic on both Postgres and SQLite, needs no dialect-specific locking, and —
critically — **does not hold a transaction open across the SMTP call**, which
the copied service does for up to 15 seconds.

A reaper moves rows whose `lease_expires_at` has passed while still `sending`
into `unknown_delivery`. Without it, a crash strands recipients in a
non-terminal state forever.

### Cancellation

The cancel endpoint transactionally marks the parent and every not-yet-claimed
recipient `cancelled`, and returns **only after the commit lands**. The UI must
not report cancellation before that: a cancel interrupted before commit is
indistinguishable from one never accepted, and reporting success would let a
resume send to people the admin believes they stopped.

The worker checks parent state before each claim, so cancel takes effect within
one send cycle. A recipient already `sending` may still be delivered — SMTP
cannot be retracted. The UI says this rather than implying a clean stop.

### Upload, preview, send

Upload parses the CSV server-side. Accept a file with or without a header row,
detecting by whether row one contains something email-shaped; with a header,
find the `email` column by name; without one, use the single column, or the
first email-shaped column. Ignore extra columns. Strip `Name <bob@x.com>`
wrappers. Canonicalize via PR 4's rules.

Duplicate handling: dedupe within the file on `email_canonical`; skip addresses
with an existing account; skip addresses holding a live invite after the reaper
has run; re-invite where the invite is expired or cancelled. The database
enforces this via PR 4's partial unique index — the check is an optimisation for
the preview, not the correctness mechanism.

The check runs at preview and again at send time, because a batch takes 25
minutes during which someone can accept an invite or self-register. The
send-time recheck is inside `claim_invite`'s transaction.

Preview shows the breakdown — *500 rows → 412 will be invited · 73 already
registered · 15 pending invite · 5 invalid · 3 duplicate rows* — with the chosen
role, and invalid rows reported with line numbers. Confirm enqueues.

The trigger endpoint inserts rows, returns `202` with a batch id, and returns.
It never sends inline.

Preflight the email configuration before accepting a batch.
`backend/services/email.py:66-77` returns `True` without sending when settings
are unconfigured; without a preflight a batch would report full success having
delivered nothing.

Send via `aiosmtplib` with an explicit timeout, following
`case_notifications.py:30`, not `fastapi_mail`. Cap batch size server-side.

### Tests

- Transport succeeds, commit fails → asserts the row is recoverable and lands in
  `unknown_delivery`, not silently re-sent. This is the case the existing suite
  omits (`tests/test_case_notifications.py:278-296` only fails *before* the
  attempt).
- Two concurrent consumers against **Postgres** → asserts exactly one claim wins.
  SQLite tests verify the state machine and must not be presented as lock
  validation.
- Cancel racing a claim.
- Lease expiry reaping into `unknown_delivery`.
- Batch resume after a worker restart.

## Out of scope

**Token and cost analytics.** Requires provider instrumentation and a schema
change, with no history to backfill. A separate track.

**Hard delete.** Would destroy the analytics from PR 2, and needs `ON DELETE SET
NULL` migrations across `invites.created_by_id` (made nullable), `wiki_pages`,
`wiki_versions`, and `knowledge_insights`. Real erasure, if ever needed, is a
deliberate anonymise-don't-destroy feature.

**Immediate WebSocket revocation on deactivation.** The hole is real
(`main.py:699-709`) but orthogonal: it is a chat-layer lifecycle concern, it
does not affect dormant users, and fixing it means mapping connections to user
IDs in `ConnectionManager` and closing them post-commit, or revalidating per
message. Deactivation semantics are documented in PR 3 rather than overclaimed.
Worth filing.

**Dark mode toggle.** `.dark` tokens exist (`index.css:16-24`) but nothing adds
the `dark` class. PR 1 repairs the values; wiring a toggle is its own project.

**Unifying the axios / raw-`fetch` split.** `AdminSettings`,
`ConfigurationChecker`, and `App.tsx` bypass the 401 interceptor
(`services/api.ts:62-78`).

**The `[object Object]` error in AdminSettings.** `handleSave` PUTs the whole
settings object, so `admin_replay_enabled` is always present; the backend raises
409 with a dict `detail`, which the frontend interpolates into a string.

**The rollout flags UI** from `docs/adr/0005`. That ADR is stale: it says the
dashboard toggles `admin_replay_enabled`; the current code has no toggle at all.

**Two Drive bugs**, worth filing: blocking `googleapiclient` calls stalling the
event loop (`drive_sync_service.py:194`, `:255`), and `stop()` not awaiting its
cancelled task (`:87-92`).

## Risks

**Duplicate email is possible and is accepted.** At-least-once means a crash in
the commit window can produce a second invite to one person. The separate
worker's stop timeout narrows it; `unknown_delivery` surfaces it; nothing
eliminates it short of relay-side idempotency keys.

**The `inferred_last_activity_at` backfill is a proxy.** A user who logs in to
read without chatting looks stale until their next login writes a true
`last_login_at`. Single-user deactivation, and showing which source produced the
timestamp, are the mitigations.

**PR 4's canonical-email migration can fail on existing data.** The audit runs
first; collisions are resolved by hand.

**PR 5 adds a systemd unit**, changing the deploy topology. `config.yaml` and
`DEPLOYMENT.md` must be updated, and the deploy must start and health-check it.

**Ordering.** PR 3 before PR 4 before PR 5. PR 5's claim invariant is PR 4's.
The `last_login_at` backfill should run soon after PR 3 so real login data
accumulates.

## Revision history

**16 July 2026 — revised after Codex adversarial review.** 15 findings, 4
blockers. Accepted 14; deferred WebSocket revocation (finding 8) to Out of
scope while accepting the demand to define deactivation semantics. Material
changes:

- Delivery is at-least-once, not exactly-once (finding 1). Added
  `unknown_delivery`, a lease reaper, and a transport-succeeds-commit-fails
  test.
- Replaced `FOR UPDATE` with a portable conditional-update lease; no
  transaction is held across SMTP; one global consumer replaces per-batch tasks
  (findings 2, 5).
- Sender moved out of the web process into its own systemd unit (finding 5).
- Added the `claim_invite` invariant, canonical email, the expiry reaper, and a
  partial unique index; split them into their own PR 4 (findings 3, 11).
- Split `0008` into an additive migration plus a separate resumable backfill,
  removing an unbounded scan from boot (finding 6).
- Separated `last_login_at` from `inferred_last_activity_at` and defined the
  stale threshold, boundary, timezone, and NULL policy (finding 7).
- Defined deactivation semantics explicitly (finding 8).
- Enum-validated `UserUpdate.role`; put the last-admin check under a lock
  (finding 9).
- Specified the pagination envelope, true counts, and sort allow-list (finding
  10).
- Bounded `days` to `{7,30,90}`, projected columns instead of whole ORM
  objects, and defined UTC boundaries, partial days, zero-fill, and NULL
  reporting (finding 12).
- **Retained `/feedback/admin`** — it is a documented deployment verification
  surface, not orphaned (finding 13).
- Specified the redirect element, added deep-link regression tests, and gated
  ChatPage's `/dashboard` link on `isAdmin` (finding 14).
- Corrected the Tailwind config path to `frontend/tailwind.config.js` (finding
  15).

Two first-draft claims were **factually wrong** and are corrected above rather
than quietly dropped: that resume could not double-send, and that deactivated
users could re-enter via an old invite link.
