# Feedback Cases and Conversation Replay

Status: Approved for implementation  
Product source: *A Loving Agent — Product Roadmap*, 30 June 2026

The external roadmap remains the product source of truth and is referenced, not
copied, here. This specification translates its approved Feedback Case,
Conversation Replay, and Execution Trace direction into repository terms.

## Product constraints

The current grounded librarian is refined before broadening the product. The
feedback loop and diagnostic replay are the priorities. New agents and parked
roadmap features remain out of scope.

## User journeys

### Authenticated chat

1. The browser opens a WebSocket and sends its current JWT and a client-created
   Chat Session UUID in the first frame.
2. The server authenticates before reading settings, history, or conversation
   data.
3. A new UUID is bound atomically to the authenticated tester. An existing UUID
   can only be resumed by its owner.
4. The owner receives chronological persisted history and continues the same
   Chat Session.

### Tester reports and follows a poor answer

1. The tester gives an assistant answer a thumbs-down rating with optional
   categories and comment.
2. The service verifies ownership of the rated answer and atomically creates
   exactly one Feedback Case in `awaiting_admin`.
3. The response supplies the case's opaque public identifier.
4. The tester can list their cases, open one, inspect the rated exchange, and
   later exchange Case Replies with administrators.
5. A thumbs-up remains aggregate feedback and creates no Feedback Case.

### Administrator diagnoses and responds

1. The administrator opens the Feedback Case queue and sees masked account
   identifiers.
2. Case detail shows the complete chronological Conversation Replay with the
   rated answer highlighted and later messages distinguished.
3. Every user-derived field passes through the fail-closed administrator
   projection. Pending or failed redaction yields no raw fallback.
4. When present, the rated answer's bounded Execution Trace shows sanitized
   tool lifecycle data. Historical answers show `trace not captured`.
5. The administrator adds an immutable Case Reply. The case moves to
   `awaiting_user`, commits, and then creates an outbound notification attempt.

### Tester and administrator correspondence

The tester's Case Reply moves the case to `awaiting_admin`. Only an
administrator can resolve a case. A tester replying to a resolved case reopens
it to `awaiting_admin`; an administrator replying to one reopens it to
`awaiting_user`. Replies are plain text, length-bounded, immutable, and ordered
by creation sequence.

## Lifecycle

```text
thumbs-down ──> awaiting_admin
admin reply ──> awaiting_user
user reply  ──> awaiting_admin
admin resolve ─> resolved

resolved + user reply  ──> awaiting_admin
resolved + admin reply ──> awaiting_user
```

Concurrent writes lock the Feedback Case before appending a reply and changing
state. Status-only resolution creates no reply.

## API contracts

All HTTP routes require a bearer JWT unless noted. Owner lookups use a
non-disclosing 404 when the resource exists for another user. Admin routes
require the admin role.

### WebSocket `/ws/{session_uuid}`

The first client frame is:

```json
{"type":"auth","token":"<jwt>"}
```

Authentication failure closes with application code `4401`; an inactive user
or ownership collision closes with `4403`. No history or configuration is read
before authentication succeeds. Existing `status`, `history`, `start`,
`think`, `chunk`, `end`, and `error` server frames remain compatible.

### Feedback and tester cases

- `POST /api/feedback` creates or updates a rating. A negative response includes
  `case_id`; a positive response does not.
- `GET /api/feedback-cases?cursor=&limit=` lists the current tester's cases.
- `GET /api/feedback-cases/{case_id}` returns the owned case, rated exchange,
  and correspondence.
- `POST /api/feedback-cases/{case_id}/replies` appends a tester reply.

List results are newest-first with an opaque cursor. Correspondence is
chronological.

### Administrative review

- `GET /api/admin/feedback-cases` lists/filter cases by responsibility state,
  category, date, and masked email.
- `GET /api/admin/feedback-cases/{case_id}/replay?cursor=&limit=` returns one
  page of fail-closed redacted replay.
- `POST /api/admin/feedback-cases/{case_id}/replies` appends an admin reply.
- `POST /api/admin/feedback-cases/{case_id}/resolve` resolves without replying.
- `POST /api/admin/case-notifications/{notification_id}/retry` retries a
  failed notification and is a no-op after confirmed delivery.

## Privacy and data boundaries

The tester is allowed to read the raw content they own. Administrative APIs
never return raw user-derived content. User messages, assistant messages,
feedback comments, source labels, and user Case Replies each carry a versioned
cached projection and `pending`, `succeeded`, or `failed` status. Local
structured recognizers plus English person/location recognition produce the
projection; no LLM participates.

Redaction is fail-closed: pending, failed, unavailable, or version-mismatched
projections return an unavailable marker, never the raw value. Email addresses
are masked in admin lists. The notification email contains only application
identity, a generic notice, and an authenticated absolute case link.

Execution Traces store ordered tool start/completion/failure facts, safe tool
names, duration, safe error category, redacted source identifiers, result
count, and bounded summaries. They exclude chain-of-thought, transient `think`
text, complete tool inputs/outputs, passages, credentials, raw exceptions, and
provider payloads. A trace is capped at 100 events and 64 KiB; truncation or
capture failure is explicit and never breaks chat streaming.

## Schema evolution, migration, and backfill

Schema changes are additive and managed by Alembic. Existing Chat Messages and
feedback are retained. A legacy Chat Session receives an owner only when all
linked feedback identifies the same single user. Conflicting, ambiguous, or
ownerless sessions are quarantined and excluded from user and admin replay.

Each eligible historical thumbs-down becomes one Feedback Case. Historical
thumbs-up remains analytics. Historical assistant messages explicitly have no
captured Execution Trace. Redaction and case backfill is resumable,
idempotent, reports processed/succeeded/failed/quarantined/pending counts, and
does not expose failed records.

Account deletion cascades through the tester's Chat Sessions, Chat Messages,
Feedback Cases, Case Replies, traces, projections, and notification records.
Deleted admin authors become null while their `Admin` role snapshot remains.

## Rollout

1. Deploy the additive schema, authenticated session ownership, and trace
   capture with both user interfaces disabled.
2. Run and verify ownership/case/redaction backfills. Admin replay cannot be
   enabled while eligible projections remain pending. Enable admin replay after
   privacy verification.
3. Verify SMTP, generic notification content, retry behavior, and authenticated
   deep links. Then enable tester correspondence and email.

Rollback disables feature flags and rolls application code back. It does not
perform a destructive database downgrade.

## Acceptance tests

- Fresh and current-schema databases reach the same migration head; rerunning
  is idempotent and migration failures stop deployment.
- WebSocket tests cover valid, missing, invalid, expired, and inactive
  authentication; owner reconnect; cross-user collision; and concurrent first
  use.
- Feedback tests cover positive/negative ratings, ownership, duplicate voting,
  pagination, login return URLs, and deletion cascade.
- Redaction tests cover structured identifiers, people, locations,
  assistant-echoed PII, filenames, model failure, fail-closed APIs, and more
  than 100 replay messages.
- Trace tests cover ordering, authorization, forbidden fields, 100-event and
  64-KiB bounds, truncation, capture failure, and historical absence.
- Correspondence tests cover every transition, admin-only resolution,
  reopening, concurrent replies, ordering, immutability, isolation, and safe
  plain-text rendering.
- Notification tests prove commit-before-send ordering, generic content,
  timeout/failure, interruption, idempotent retry, already-sent behavior,
  disabled SMTP, and deep-link return.
- Backfill/rollout tests cover conflicting ownership, partial restart, flag
  combinations, readiness gates, additive rollback, and deletion of migrated
  and new records.

## Out of scope

- New assistant agents or expansion beyond the grounded librarian
- Multi-session creation/list management
- Case assignment or admin email alerts
- Inbound email and reply-by-email
- Editing or deleting Case Replies
- LLM-based redaction
- Reconstruction of historical Execution Traces
- Destructive schema rollback
- Other features parked by the 30 June 2026 roadmap

