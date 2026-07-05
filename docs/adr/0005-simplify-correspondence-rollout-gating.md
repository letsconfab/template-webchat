# ADR-0005: Simplify the tester-correspondence rollout gating

- **Date:** 2026-07-05
- **Status:** Proposed

## Context

Admin-to-tester correspondence (sending a Case Reply and delivering it by
email) is currently guarded by three independent booleans on
`system_settings`:

- `admin_replay_enabled` — gates the replay/case view the reply is authored from.
- `tester_correspondence_enabled` — gates reply creation and case resolution.
- `tester_email_notifications_enabled` — gates whether the notification is
  actually emailed.

The reply route requires the first two (`admin_feedback_cases.py`), while the
notification service independently requires the third and general
`email_notifications_enabled` in `_configured()` (`case_notifications.py`).
None of these three flags has an admin UI control — `AdminDashboard` only
toggles `admin_replay_enabled`. Enabling correspondence in production therefore
depends on an out-of-band `PUT /api/settings/current` call (or raw SQL) that is
not part of the deploy and is easy to forget; the migration only adds the
columns with `server_default false`.

This produced a live incident: after a successful deploy, admins saw
"Correspondence is not enabled…" and could not reply, because the two tester
flags were still `false`. The split also permits a silent half-enabled state —
if only `tester_correspondence_enabled` were set, replies would save but the
email would be dropped as `disabled_configuration` with no operator signal.

The frontend duplicates the backend gate: `AdminFeedbackCasesPage` fetches
`/settings/features`, disables the reply box, and shows a static
"until the production rollout is completed" message, while the backend
independently returns `404 Feature not enabled`. The user-facing copy does not
distinguish "not rolled out yet" from "email delivery is misconfigured".

## Decision

Collapse correspondence gating to a **single capability** and make it
operable and observable:

1. Represent the tester-correspondence capability with one flag (retain
   `tester_correspondence_enabled` as the switch; treat email delivery as an
   implementation detail of an enabled capability rather than a second gate).
   Fold the `tester_email_notifications_enabled` check into the same capability
   or derive it, so an enabled capability with unusable SMTP surfaces as a
   *configuration error*, never a silent drop.
2. Expose the switch in `AdminDashboard` alongside `admin_replay_enabled`,
   with the same readiness gating the backend enforces, so rollout is a
   self-serve admin action instead of an undocumented API/SQL step.
3. Make the frontend gate derive from a single `/settings/features` field and
   render distinct messages for "capability disabled" versus
   "email delivery misconfigured", instead of one static rollout string.

## Consequences

Rollout becomes a single, discoverable toggle with no out-of-band call, and the
half-enabled state that drops emails silently is eliminated. The
dependency between correspondence and its email transport becomes explicit in
one place rather than split across the reply route and the notification
service. Existing prod rows that set the flags independently must be
reconciled when the flags are consolidated (a data migration or a compatibility
read that treats either legacy flag as the single capability). The immediate
incident is still resolved out-of-band by enabling both current flags; this ADR
governs the follow-up cleanup, not the hotfix.
