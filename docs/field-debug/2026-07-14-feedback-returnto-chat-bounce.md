# Field debug: feedback `returnTo` still lands on `/chat`

- Report timestamp: `2026-07-14T22:54:29Z`
- Implementation readiness: `READY`
- Severity: medium (deep-link from email / shared login URL fails; chat still works)
- Status: ongoing for the reported path; production otherwise healthy
- Symptom: opening or completing login for `https://alochat.platform.confabs.org/login?returnTo=%2Ffeedback%2Fa7b7c2df-a857-42fc-880c-a771328dc5a8` ends at `https://alochat.platform.confabs.org/chat`
- Expected: after authentication, land on `/feedback/a7b7c2df-a857-42fc-880c-a771328dc5a8` and render the case
- Environment / target / components: `production` / `webchat` / frontend auth + route guards (`AdminLogin`, `ProtectedRoute`, `AuthContext`, axios client)
- Deployed source: `4e761215dbe94a4962dbd1d150326fdb7ba3ccd0` (frontend asset `index-BseP2e-q.js`)
- First known bad (this retry): `2026-07-14T22:46:40Z` post-login trace
- Last known good for same case API: `2026-07-14T18:20:35Z` (`GET /api/feedback-cases` 200 after login)
- Supported cause (confidence: **high**): post-login navigation took AdminLogin’s role-default branch to `/chat` because `returnTo` was not available from query or `sessionStorage` at navigation time. A proven contributor is the axios 401 handler hard-redirecting to bare `/login`, which strips `returnTo`.

## 2. Safety and target state

- Public `/health`: healthy
- Host HEAD: `4e76121`; `webchat` active
- Rollout flags in `system_settings`: all three enabled (`admin_replay_enabled`, `tester_correspondence_enabled`, `tester_email_notifications_enabled`)
- Case `a7b7c2df-a857-42fc-880c-a771328dc5a8` exists (`awaiting_user`, owner `user_id=21`, role `user`)
- No active deployment run (`.tmt-agent-deploy` status idle)
- Blast radius: tester feedback deep links / post-login return paths only
- Data integrity: unaffected
- Rollback / emergency action: not required for investigation
- Constraints honored: read-only probes only (curl, SSH journal/SQL selects, browser anonymous observation). No deploys, restarts, flag changes, or code edits.

## 3. Evidence index

| ID | UTC timestamp/window | Source | Sanitized query or reference | Observation | Reliability |
|---|---|---|---|---|---|
| E1 | 2026-07-14T16:58:55Z run | `.tmt-agent-deploy/runs/20260714T165855Z-production-0f8aa05.md` | deploy summary | Release `4e76121` / asset `index-BseP2e-q.js` shipped successfully | high |
| E2 | 2026-07-14T22:48Z | curl health/asset/host | `curl /health`; `curl /assets/index-BseP2e-q.js`; `git rev-parse HEAD` | healthy; asset 200; host at `4e76121` | high |
| E3 | 2026-07-14T22:48Z | bundled JS symbol scan | count `featuresLoaded`, `postLoginReturnTo`, `tester_correspondence_enabled` | Prior race fix is present in production bundle | high |
| E4 | 2026-07-14T22:48Z | SQL read-only | `SELECT … FROM system_settings LIMIT 1` | All correspondence/replay flags `true` | high |
| E5 | 2026-07-14T22:48Z | SQL read-only | case by `public_id` | Case exists; status `awaiting_user`; owner role `user` | high |
| E6 | 2026-07-14T22:50:00Z | browser anonymous probe | open login URL with `returnTo` | Stays on login form; token absent; URL retains `returnTo` | high |
| E7 | 2026-07-14T22:46:40Z | `journalctl -u webchat` | login → me → features → chat-config → `/ws/chat` | No `feedback-cases` request after the failing login; ChatPage mounted immediately | high |
| E8 | 2026-07-14T22:25:02Z | same journal | `POST … 401` then `GET /login` | Axios 401 path hard-navigates to bare `/login` (no `returnTo`) | high |
| E9 | 2026-07-14T17:23Z / 18:20Z | same journal | login then `GET /api/feedback-cases…` 200 | Same-day successful feedback navigations exist when return path is intact | high |
| E10 | repo | `frontend/src/services/api.ts` | 401 interceptor | `window.location.href = '/login'` drops query/state except surviving `sessionStorage` | high |
| E11 | repo | `frontend/src/pages/AdminLogin.tsx` | post-login `useEffect` | If neither query nor session value exists → non-admin goes to `/chat`; session key is removed on read | high |
| E12 | repo | `frontend/src/components/ProtectedRoute.tsx` | feature gate | Feature-off bounce also targets `/chat`, but only after `featuresLoaded` | high |

Negative evidence: production flag-off and missing `featuresLoaded` deploy are both contradicted by E3/E4.

## 4. Timeline

- `16:58:55Z` — deploy `4e76121` with `featuresLoaded` wait + login hydration ordering (E1, E3).
- `17:23` / `18:20` — successful post-login feedback API access (E9).
- `22:25:02Z` — authenticated call returns 401; browser loads bare `/login` (E8, E10).
- `22:46:02Z` — SPA `config-status` on an already-loaded client.
- `22:46:40Z` — user login succeeds; next app traffic is chat-config + chat WebSocket; no feedback-cases (E7).
- `22:50:00Z` — anonymous open of the reported `login?returnTo=…` URL remains on login (E6).
- Now — service healthy; flags on; bug still reproducible for the reporter’s auth path (E2, E4).

## 5. Reproduction or observable signature

**Deployed-path signature (failing):** after `POST /api/auth/login` 200 for the deep-link attempt, the next authenticated document/API traffic is `GET /api/settings/chat-config` and `WebSocket /ws/chat`, with **zero** `GET /api/feedback-cases/{id}`.

**Safe observation (done):**
1. Confirm bundle/host/flags (E2–E5).
2. Open the reported login URL logged-out (E6) — form only; no auto-jump to `/chat`.
3. Compare journal around the user retry (E7).

**Expected failing result:** final location `/chat`; journal matches E7.

**Observed:** E6 shows logged-out entry is fine; E7 shows the authenticated completion path failed by skipping feedback entirely.

**Frequency:** at least one clear failure at `22:46:40Z` after deploy; earlier same-day successes show it is path-dependent, not a total outage.

**Limitation:** this skill did not submit the reporter’s credentials, so a live authenticated browser repro was not completed here. Journal signature + code paths are sufficient for a READY fix brief.

## 6. Hypothesis ledger

| Rank | Hypothesis and prediction | Probe | Evidence | Result | Status |
|---|---|---|---|---|---|
| H1 | `tester_correspondence_enabled` is false → ProtectedRoute bounces `/feedback` → `/chat` | Read `system_settings`; expect false | E4 true; E9 same-day feedback API success | Flag is on | **falsified** |
| H2 | Production missing `featuresLoaded` fix → default flags bounce | Scan live `index-BseP2e-q.js` | E3 symbols present; host `4e76121` | Fix deployed | **falsified** |
| H3 | Logged-out open of `login?returnTo` immediately routes to `/chat` | Anonymous browser open | E6 stayed on login | Not immediate | **falsified** |
| H4 | Post-login AdminLogin defaults to `/chat` because `returnTo` missing from query and session | Journal should show chat APIs and no feedback-cases | E7 exact match; E11 default branch | Supported | **supported** |
| H5 | Axios 401 hard redirect to `/login` strips `returnTo`, leaving a bare login that later defaults to `/chat` | Journal around 401; read interceptor | E8 + E10 | Supported contributor | **supported** |
| H6 | Feature gate still races after login despite ordering | Would expect `/feedback` navigation then bounce; features body unknown | E7 has no feedback-cases (compatible with bounce **or** never navigating to feedback). Flags true weakens “stable false flag” | Possible secondary | **weakened** |

## 7. Causal analysis

### Observed facts

- Live code includes the earlier feature-loading guard and login hydration order (E3).
- Rollout flags are enabled (E4).
- The failing login never fetched the feedback case; it fetched chat config and opened the chat socket (E7).
- AdminLogin’s fallback for a non-admin without `returnTo` is `/chat` (E11).
- A 401 response hard-sets `location` to `/login` with no query (E8, E10).
- Logged-out navigation to the reported URL does not alone cause `/chat` (E6).

### Supported inference

The user-visible `/chat` landing is AdminLogin choosing the **role default**, not ChatPage inventing a redirect. That happens when both `searchParams.returnTo` and `sessionStorage.postLoginReturnTo` are empty at the moment `user` becomes truthy. The axios 401 interceptor is a concrete, production-proven way to erase the query form of `returnTo`. Session recovery is then a single destructive read in AdminLogin; if that value is absent too, `/chat` is guaranteed.

### Unverified remainder

- Whether the `22:46:40Z` attempt specifically lost `returnTo` via a preceding 401, a bare `/login` paste, or another client navigation was not captured in the immediate pre-login document log.
- Whether a ProtectedRoute feature bounce also occurred in the same tick cannot be separated from “never navigated to `/feedback`” using API logs alone when feedback-cases is absent either way. Given E4, a stable flag-off bounce is unlikely.

### Why deploy smoke missed it

Smoke checked `/health`, the JS asset, and unauthenticated `401` on an admin API. It did not exercise logged-out → login → `/feedback/:id` retention.

## 8. Suggested fixes

1. **`required` — preserve deep link across 401 handling** (`frontend/src/services/api.ts`)
   - On 401, if current path is not an auth page, set `localStorage`/`sessionStorage` return target and redirect to `/login?returnTo=…` (encoded current path+search), or at least `/login?returnTo=` from the current location.
   - Do not hard-redirect when already on `/login` (avoid loops / wiping an existing `returnTo`).
   - Addresses E8/E10/H5.

2. **`required` — make AdminLogin return-target resolution idempotent** (`frontend/src/pages/AdminLogin.tsx`)
   - Resolve `returnTo` once into a ref/state on mount and whenever search changes.
   - Do not `removeItem('postLoginReturnTo')` until navigation to a non-login destination has been committed (or stop clearing when query already has `returnTo`).
   - Wait for `!isLoading` (and, for feature-gated targets, `featuresLoaded`) before auto-navigation when `user` is set.
   - Addresses E7/E11/H4 and hardens H6.

3. **`validation` — regression tests**
   - Axios/unit test: 401 from a protected path preserves return target; 401 on `/login` does not strip an existing `returnTo`.
   - AdminLogin/integration: sessionStorage-only return target still wins over `/chat`; effect re-running after storage clear must not fall through if query/ref still holds the path.
   - Keep existing `PostLoginRedirect.test.tsx` / `ProtectedRoute.test.tsx` green.

4. **`hardening` — prefer email link entry via `/feedback/:id`**
   - Already true server-side (`case_notifications.py` uses `/feedback/{id}`). Document HITL using `scripts/debug-feedback-deeplink-hitl.sh` after the fix.

5. **`cleanup` — none required** on the host for this incident.

Alternatives considered:
- Disabling the ProtectedRoute feature gate for `/feedback/:id`: rejected; would bypass intentional rollout control and is unnecessary while flags are on.
- Only re-deploying current build: rejected; E3 shows the previous fix is already live.

Risks: 401 redirect changes must avoid open redirects (allow only same-origin relative paths starting with `/` and not `//`). No migration/data risk.

## 9. Implementation brief

### Objective

A logged-out user who authenticates in order to open `/feedback/<caseId>` (via `returnTo` query and/or `postLoginReturnTo`) must end on that feedback URL, not `/chat`, including after an intervening 401 that forces re-login.

### Required changes

1. Update `frontend/src/services/api.ts` response interceptor (E10) to preserve return path on 401 (section 8.1).
2. Update `frontend/src/pages/AdminLogin.tsx` post-login effect (E11) for idempotent return-target handling and loading gates (section 8.2).
3. Add/extend frontend tests listed in section 8.3; reuse case id `a7b7c2df-a857-42fc-880c-a771328dc5a8` already used in `ProtectedRoute.test.tsx`.

### Acceptance criteria

- Logged-out visit to `/feedback/<id>` → login with `returnTo` → sign-in → final path `/feedback/<id>`.
- Direct `/login?returnTo=/feedback/<id>` → sign-in → final path `/feedback/<id>`.
- Simulated 401 while on `/feedback/<id>` lands on login **with** return target retained; after sign-in, back to `/feedback/<id>`.
- Non-deep-link login for a normal user may still go to `/chat`.
- Admin deep links remain admin-safe (no open redirect).
- Existing feature-flag gating while `featuresLoaded === false` still shows spinner, not `/chat`.

### Test plan

- Pre-fix assertion: AdminLogin with authenticated user, empty query, empty sessionStorage → `/chat` (documents current default).
- Pre-fix assertion: 401 interceptor assigns bare `/login`.
- Post-fix: tests in 8.3 fail before / pass after.
- Non-production: run `frontend` vitest for the touched files; optional HITL via `scripts/debug-feedback-deeplink-hitl.sh` against staging or production only with separate deploy auth.
- Post-deploy observation (not authorized here): journal after login must show `GET /api/feedback-cases/<id>` before any chat WebSocket for the deep-link attempt.

### Non-goals

- Changing rollout flag semantics or enabling flags.
- Backend email URL format changes.
- Redeploying without the code fix.
- Broad auth rewrite.

### Risks and constraints

- Must keep return URL validation (`startsWith('/') && !startsWith('//')`).
- Avoid login redirect loops on 401 from `/api/auth/login` itself.
- StrictMode is enabled (`frontend/src/main.tsx`); effect logic must be idempotent.

### Implementation inputs

- Source identity: `4e76121` currently live; implement on top of current `main`/branch tip.
- Files: `frontend/src/services/api.ts`, `frontend/src/pages/AdminLogin.tsx`, tests under `frontend/src/**`
- Evidence: E7, E8, E10, E11
- HITL helper: `scripts/debug-feedback-deeplink-hitl.sh`
- Runbook: `DEPLOYMENT.md` (feedback rollout section) — informational only

## 10. Open questions and blockers

None for implementation readiness. Optional confirmation from the reporter: immediately before clicking Sign In at `22:46Z`, did the address bar still include `returnTo=…`? That only refines which contributor dominated; the required fixes cover both strip and fallback paths.

## 11. Readiness and next authorization

`READY` for `implement`.

Next authorization requested: **implement the required frontend fixes** (separate from any later deploy authorization).
