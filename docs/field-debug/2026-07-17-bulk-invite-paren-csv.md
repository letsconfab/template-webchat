# Field debug: bulk invite CSV fails on `Name (email)` rows

- Report timestamp: `2026-07-17T15:22:26Z`
- Implementation readiness: `READY`
- Severity: high for first production bulk invite (11/12 failed; 0 sent); production otherwise healthy
- Status: batch `#1` terminal (`completed`); residual bogus pending invites remain; parser defect still live
- Symptom: Admin “Bulk invite (CSV)” batch `#1` finished with **Total 12 / Failed 11 / Skipped 1 / Sent 0**. Failed rows render with parentheses around the address (e.g. `(…@…)`).
- Expected: `Name (email@domain)` contact-style cells yield bare addresses, enqueue, and SMTP-send (or skip for genuine pending/registered), matching the angle-bracket behavior already specified.
- Environment / target / components: `production` / `webchat` + `webchat-invite-worker` / CSV parse (`extract_email` / `parse_csv_bytes`) → recipient enqueue → invite claim → `smtp_invite_transport`
- Deployed source: `fd26cb044edbed7d4f7ed0874b3afce8ff8daf05` (frontend asset `index-CAvaqpjH.js`; migration head `0010_invite_batches`)
- First known bad: `2026-07-17T14:31:48Z` (first invite-worker SMTP warning for batch `#1`)
- Last known good for bulk invite path: none observed (first production batch)
- Supported cause (confidence: **high**): `extract_email` accepts parentheses as part of the address because `_BARE_EMAIL` / `_EMAIL_SHAPE` allow `(` / `)`. Contact-style CSV cells become stored recipients like `(user@domain)`, `EmailMessage["To"]` silently drops them, and aiosmtplib fails with `No recipient headers provided in message` → `hard_reject`.

## 2. Safety and target state

- Public `/health`: healthy (`200`)
- Frontend asset `index-CAvaqpjH.js`: `200`
- Host HEAD: `fd26cb0`; `webchat` active; `webchat-invite-worker` active
- No active deployment run (`.tmt-agent-deploy/state/current-run.yaml` absent; latest run `20260716T234854Z-production-63239da` finalized `failed` on a post-restart smoke race; live release retained)
- Blast radius: CSV bulk invites only; single-invite path unaffected unless the same malformed string is typed
- Data integrity: **residual** — 11 `invites` rows with `status=pending` and paren-leading addresses linked to batch `#1` recipients (created before SMTP failed). Correct bare addresses are **not** blocked by these rows (canonical differs). Separate cleanup authorization required to cancel them.
- Rollback / emergency action: not required for investigation; do not roll back `fd26cb0` for this defect
- Constraints honored: read-only probes only (public curl, SSH status, sanitized SQL aggregates, journal with emails redacted). No deploys, restarts, flag changes, data mutation, or product-code edits.

## 3. Evidence index

| ID | UTC timestamp/window | Source | Sanitized query or reference | Observation | Reliability |
|---|---|---|---|---|---|
| E1 | 2026-07-16T23:48:54Z | `.tmt-agent-deploy/runs/20260716T234854Z-production-63239da.md` | deploy summary | Release `fd26cb0` / asset `index-CAvaqpjH.js` / migration `0010` / invite-worker installed; smoke race marked failed; no rollback | high |
| E2 | 2026-07-17T15:22Z | public curl | `GET /health`; `GET /assets/index-CAvaqpjH.js` | healthy `200`; asset `200` | high |
| E3 | 2026-07-17T15:22Z | SSH host | `git rev-parse HEAD`; `systemctl is-active webchat webchat-invite-worker` | `fd26cb0`; both `active` | high |
| E4 | user upload + screenshot | CSV + UI batch `#1` | file `Bulk Invite Uploaded July 17, 2026 - Sheet1.csv`; UI totals | 12 rows; header `email`; 11 `Name (addr)` cells + 1 bare email; UI failed rows show paren-wrapped addresses; 1 skipped bare address | high |
| E5 | 2026-07-17 local repro | mirrored `extract_email` regexes from live module | parse uploaded CSV | 11 rows extract to `(user@domain)` (or leading-`(` without closing on last line); 1 bare address extracts cleanly; `_EMAIL_SHAPE` accepts paren forms | high |
| E6 | 2026-07-17T15:22Z | SQL read-only | `invite_batches` / `bulk_invite_recipients` aggregates for `batch_id=1` | `completed` 12/0/11/1; 11 `failed`/`hard_reject` (10 fully `(…)` wrapped; line 13 leading-`(` only); 1 `skipped`/`pending_invite` with no `()` | high |
| E7 | 2026-07-17T14:31:48Z–14:32:25Z | `journalctl -u webchat-invite-worker` | SMTP warnings for recipients 1–11 | `Bulk invite SMTP failed for recipient N: No recipient headers provided in message` (11 events) | high |
| E8 | 2026-07-17 local | `email.message.EmailMessage` | set `To` to `(user@domain)` vs bare | paren forms set `To` to empty; bare address retained | high |
| E9 | 2026-07-17T15:22Z | SQL read-only | invites joined to batch `#1` | 11 `pending` invites, all paren-leading; 11 paren-leading pending invites total in DB | high |
| E10 | repo + host | `backend/services/bulk_invites.py` | `_ANGLE_EMAIL`, `_BARE_EMAIL`, `_EMAIL_SHAPE`, `extract_email`, `smtp_invite_transport` | Angle wrappers only; bare regex allows `()`; shape allows `()`; transport assigns `message["To"] = recipient` then `aiosmtplib.send` | high |
| E11 | repo | `docs/specs/admin-dashboard-ui-ux.md` §PR5 upload | “Strip `Name <bob@x.com>` wrappers” | Spec covers angle form only; paren/contact export form unspecified | high |
| E12 | CSV bytes | local file read | last data line hex | Last line missing closing `)`: `Dongxuan Hou (houdongxuan3@gmail.com` | high |

Negative evidence: SMTP/config outage and invite-worker downtime are contradicted by E2/E3 and by the one successful skip path (`pending_invite`) on the bare address (E6).

## 4. Timeline

- `2026-07-16T23:48:54Z` — deploy `fd26cb0` with bulk-invite schema + invite-worker; smoke race failed; release retained (E1).
- `2026-07-17` morning (operator) — first CSV upload of contact-style sheet (E4).
- `2026-07-17T14:31:48Z`–`14:32:25Z` — worker processes 11 recipients; each SMTP attempt fails with missing recipient headers; terminal `hard_reject` (E6, E7).
- Same window — bare address row skipped as `pending_invite` without SMTP (E6).
- Batch reaches `completed` with sent=0 (E4, E6).
- `2026-07-17T15:22Z` — field-debug probes confirm healthy services, residual 11 paren pending invites, live regexes unchanged (E2, E3, E9, E10).

## 5. Reproduction or observable signature

**Deployed-path signature (failing):** after CSV confirm for cells like `Ada Lovelace (ada@example.com)`, stored `bulk_invite_recipients.email` is `(ada@example.com)`; invite-worker logs `No recipient headers provided in message`; recipient ends `failed` / `hard_reject`.

**Safe observation (done):**
1. Public health + host identity (E2, E3).
2. Sanitized batch/recipient aggregates and paren-shape flags (E6).
3. Redacted invite-worker journal window (E7).
4. Local parse of the operator CSV with production regexes (E5, E12).
5. Local `EmailMessage` To-header drop for paren addresses (E8).

**Expected failing result:** matches E4–E8.

**Frequency:** 11/11 paren-derived recipients in batch `#1`; 0/1 bare address failed for this reason.

**Limitation:** no new mutating upload was performed. Residual invites (E9) must not be cancelled under this skill.

## 6. Hypothesis ledger

| Rank | Hypothesis and prediction | Probe | Evidence | Result | Status |
|---|---|---|---|---|---|
| H1 | Invite worker down / SMTP unconfigured → all sends fail | systemd + health; expect inactive or `disabled_configuration` | E3 active; E6 category `hard_reject` not disabled; one skip succeeded | Not config outage | **falsified** |
| H2 | Addresses invalid at preview and should have been `invalid` rows | Parse CSV; expect `invalid_reason` | E5 extracts paren forms as “valid”; batch enqueued 12 rows | Accepted as valid | **falsified** as preview-invalid |
| H3 | CSV `Name (email)` kept parentheses because extractor only strips `<>` and regexes allow `()`; SMTP To header then empty | Local extract + EmailMessage + DB shape + journal text | E5, E6, E7, E8, E10 | Exact match | **supported** |
| H4 | Failures are ordinary SMTP 550 hard rejects for real mailboxes | Journal / category | E7 text is missing headers, not 550; EmailMessage drops To (E8) | Not mailbox reject | **falsified** |
| H5 | Skipped row proves worker/path works for bare emails | Recipient summary | E6 `skipped`/`pending_invite` on non-paren row | Path works when address is bare | **supported** (contrast) |

## 7. Causal analysis

**Observed facts**
- Uploaded cells are mostly `Display Name (email@domain)`; one bare email; last line missing `)` (E4, E12).
- Live `extract_email` only special-cases `Name <email>`; `_BARE_EMAIL` / `_EMAIL_SHAPE` permit `()` (E5, E10).
- Batch `#1` stored paren-leading emails, failed them as `hard_reject`, skipped the bare pending invite (E6).
- Worker errors are `No recipient headers provided in message` (E7); `EmailMessage` clears invalid paren `To` values (E8).
- Invite rows were claimed before SMTP, leaving 11 pending paren invites (E9).

**Supported inference**
Contact-export CSV format entered the “email” column. The parser treated `(user@domain)` as a legal address, enqueued it, created a pending invite for that literal string, then failed SMTP because the message had no usable `To` header. The UI therefore shows failed emails still wrapped in parentheses.

**Unverified remainder**
- Exact client library path inside aiosmtplib that raises the precise string (behavior is still determined by empty recipient headers).
- Whether preview UI made the paren samples obvious enough for the operator (not required to fix the parser).

**Why preflight/smoke missed it**
Deploy smoke covers `/health`, asset, API 401, migration head, and worker active — not CSV fixture formats. Spec/tests cover `Name <email>` only (E11; unit tests), so `Name (email)` never exercised.

**Residual state**
11 pending invites with paren-leading addresses remain. They do not block a corrected re-upload of bare emails, but they are junk and should be cancelled under separate cleanup authorization.

## 8. Suggested fixes

1. **required — accept and strip `Name (email)` wrappers; reject `()` inside extracted addresses**
   - Files/symbols: `backend/services/bulk_invites.py` — `extract_email`, `_EMAIL_SHAPE`, `_BARE_EMAIL` (add `_PAREN_EMAIL` or equivalent); keep angle-bracket path.
   - Behavior: for `Ada (ada@x.com)` return `ada@x.com`; never return a string containing `()`; incomplete wrappers still recover the bare address via tightened bare match when possible; otherwise `invalid`.
   - Evidence: E4–E8, E10–E12.
   - Alternatives considered: document “emails only” and reject name wrappers — ranks lower because angle form is already supported and contact CSVs commonly use parentheses. Relying only on SMTP failure — ranks lower (creates junk invites first).

2. **validation — regression tests for the failing CSV shapes**
   - Files: `tests/test_bulk_invites.py` (`CsvParseUnitTests`).
   - Cases: `Name (a@b.co)`; bare email; `Name <a@b.co>`; mixed column; missing closing `)`; assert extracted canonicals and that paren literals are not “valid”.
   - Optional: transport/unit assert that a paren recipient cannot be treated as success (if cheap).

3. **hardening — fail closed before claim/SMTP when `To` would be unusable**
   - After extract, validate with the same rules `EmailMessage` accepts (or `email.utils.parseaddr` round-trip requiring non-empty addr and no `()` / `<>` residue).
   - Mark as `invalid` / do not enqueue rather than creating invites that can never send.
   - Evidence addressed: E8, E9.

4. **cleanup — cancel residual paren pending invites from batch `#1`**
   - Operational/data change on production `invites` (11 rows). Requires **separate destructive authorization**; not part of code implement.
   - Rollback N/A; risk is low if scoped to `left(email,1)='(' AND status='pending'`.

**Compatibility / security / ops**
- Backward compatible for bare and angle-bracket CSVs.
- No secret handling change.
- After code deploy, operator can re-upload a corrected CSV; cleanup of junk invites is independent.

## 9. Implementation brief

### Objective

Bulk invite CSV cells in `Name (email@domain)` form (and incomplete paren wrappers) must enqueue and send using the bare address; parentheses must never be stored as part of `email` / `email_canonical`.

### Required changes

1. Update `extract_email` in `backend/services/bulk_invites.py` to strip parenthetical emails (mirror angle-bracket handling) **before** bare-shape acceptance (E5, E10, E11).
2. Tighten `_EMAIL_SHAPE` and `_BARE_EMAIL` so `(` and `)` cannot appear in a matched address (E5, E8, E12).
3. Ensure `parse_csv_bytes` continues to mark true non-emails invalid; do not enqueue paren literals (E6).
4. Add unit tests in `tests/test_bulk_invites.py` covering the operator CSV patterns (E4, E12).
5. (Implementation-time discovery, optional hardening) Add a post-extract guard that refuses addresses `EmailMessage` would drop, so claim/SMTP never runs on unusable `To` values (E8, E9).

### Acceptance criteria

- Parsing `Name (user@domain)` yields `user@domain` / canonical lowercased bare form.
- Parsing the attached CSV shape yields 11 bare invites + 1 bare address (subject to skip rules), with **zero** stored emails containing `()`.
- `Bob <bob@x.com>` and bare `bob@x.com` behavior unchanged.
- Incomplete `Name (user@domain` still extracts `user@domain` when the bare address is present.
- Strings that are not recoverable emails remain invalid with line numbers.
- Existing lease/cancel/worker tests still pass.
- No production data mutation in the code change itself.

### Test plan

- **Regression seam:** `CsvParseUnitTests` / `extract_email` + `parse_csv_bytes`.
- **Pre-fix failing assertion:** `extract_email("Ada (ada@example.com)") == "(ada@example.com)"` today; change expectation to `"ada@example.com"`.
- Focused tests for angle, paren, bare, missing `)`, header `email` column.
- Run `tests/test_bulk_invites.py` (full bulk-invite suite).
- Non-production rehearsal: preview/confirm a fixture CSV with mixed formats against local stack; confirm preview samples show bare addresses.
- Post-deploy smoke (not authorized here): upload a tiny fixture with one `Name (addr)` row to a non-prod or carefully scoped prod test address; expect `sent` or authentic skip — not `hard_reject` with paren UI. Observe invite-worker journal for absence of `No recipient headers provided in message`.

### Non-goals

- Redesigning bulk-invite UI/UX beyond what is needed to display correct emails.
- Changing SMTP provider settings or worker pacing.
- Cancelling residual production invites (separate cleanup auth).
- Supporting arbitrary free-text cells beyond recoverable email extraction.
- Rolling back `fd26cb0`.

### Risks and constraints

- Residual 11 paren pending invites remain until cleanup authorization.
- Re-upload after fix will invite the real bare addresses; operators should not assume batch `#1` recipients were notified.
- Over-tight email regexes could reject unusual but legal local-parts; prefer excluding `()<>` / whitespace rather than inventing a full RFC parser unless hardening uses stdlib parsing carefully.
- Deploy of the fix is a separate `tmt-agent-deploy` authorization from this brief.

### Implementation inputs

- Deployed commit: `fd26cb044edbed7d4f7ed0874b3afce8ff8daf05`
- Primary module: `backend/services/bulk_invites.py` (`extract_email`, regexes, `smtp_invite_transport`)
- Tests: `tests/test_bulk_invites.py`
- Spec note: `docs/specs/admin-dashboard-ui-ux.md` (extend strip rule to parentheses when implementing docs touch is desired; not required for fix)
- Evidence IDs: E4–E12
- Safe local repro: mirror regex extract against the operator CSV (no secrets)
- Production read-only queries already used (aggregates only; do not log raw emails)

## 10. Open questions and blockers

None for implementation readiness. Cleanup of the 11 residual pending paren invites is an operational follow-up requiring separate authorization, not a code blocker.

## 11. Readiness and next authorization

`READY` — pass this report to `implement` for the parser/validation fix and tests.

**Next authorization requested:** implement the required + validation changes in-repo (no deploy, no production data cleanup). After merge/deploy authorization, separately authorize cancelling the 11 residual paren-leading pending invites.
