# Field debug: admin dashboard shows zero invites/users after the 2026-09-22 rollback

## 1. Incident summary

- **Report time:** 2026-09-28 00:35 UTC (2026-09-27 20:35 EDT)
- **Implementation readiness:** `READY`
- **Severity / status:** High (admin visibility lost; no data loss). Ongoing since 2026-09-22 22:11 UTC.
- **Symptom:** `https://alochat.platform.confabs.org/admin/dashboard` shows Total/Accepted/Pending invites = 0 and "No invites sent". **Expected:** 65 invites and 26 users from production data.
- **Environment:** production, single EC2 host, `webchat` systemd service behind Caddy; Postgres `webchat-db` in Docker.
- **Deployed source:** backend checkout `90a176d0d05244ed9aa778a861fc793c8ef6a09b` (Alembic head `0011_sessions_journeys`). The **frontend served is `index-CuA7AIXC.js`**, a 2026-07-04 build. It is not `index-JNY7hdXb.js`, the recorded frontend for `90a176d`.
- **Last known good:** before deployment run `20260922T220910Z-production-ee7fba5` (2026-09-22 ~22:09 UTC). **First known bad:** 2026-09-22 22:11:36 UTC, when the rollback rewrote `frontend/dist/index.html`.
- **Supported cause (high confidence):** this is not data loss. The failed deploy's rollback restored the retained July 28 frontend and then ran `git reset --hard 90a176d`. That reset rewrote the tracked but stale `frontend/dist/index.html`, which points to the July 4 bundle. The July 4 dashboard reads `response.data.invites`. The current API returns `items`, so the dashboard falls back to `[]` and shows 0.

## 2. Safety and target state

- `/health` is 200 `{"status":"healthy"}`. `webchat` and `webchat-invite-worker` are active, with 0 restarts since 2026-09-22 22:11:39 UTC (E2).
- **Data integrity: intact.** Postgres has been running since 2026-06-16, and the container has been up for 3 months without being recreated. The rows are all present, with activity as recent as 2026-09-26 (E3, E4).
- No deployment is in progress; `.tmt-agent-deploy/state/current-run.yaml` is absent (E1).
- Blast radius: every browser user gets a July 4 frontend running against a July 28 backend. The admin dashboard is confirmed broken. Other pages whose API contracts changed between `e914e6f` and `90a176d` are probably affected too (unverified). Feedback summary pages from `3c5aa20` are probably missing.
- Disk on `/` is 95% used, with 1.7 GiB free (E2). This is a separate, standing risk, and it is what blocks the next deploy.
- No emergency rollback is needed. A single-file frontend restore fixes the symptom (see §8 F1).
- All field probes were read-only: `curl`, `git log/status/show`, `df`, `free`, `systemctl is-active/show`, `docker ps`, `journalctl` grep, `stat`/`grep` on dist files, and `SELECT count(*)` in a read-write-off check session.

## 3. Evidence index

| ID | UTC timestamp/window | Source | Sanitized query or reference | Observation | Reliability |
|---|---|---|---|---|---|
| E1 | 2026-09-22 22:09–22:13 | Local run record | `.tmt-agent-deploy/runs/20260922T220910Z-production-ee7fba5.md` | Deploy of `841d8ae` failed at the disk preflight (1,793,597,440 B free, 4 GiB needed). No venv, migration, or systemd change happened. The rollback restored the bundle, ran `reset --hard 90a176d`, and restarted. Rollback verification checked `/health` only. | High |
| E2 | 2026-09-28 00:28 | Host | `git log -1`; `df -h /`; `systemctl show webchat`; `docker ps -a` | HEAD=`90a176d`; disk 95% used, 1.7G free; webchat active since 2026-09-22 22:11:39; `webchat-db` up 3 months (healthy) | High |
| E3 | 2026-09-28 00:30 | Postgres | `select count(*), max(created_at)` on users, invites, chat_sessions, chat_messages, feedback_cases, invite_batches | 26 / 65 / 55 / 273 / 24 / 2 rows; latest writes 2026-09-26 23:26 | High |
| E4 | 2026-09-28 00:30 | Postgres | `alembic_version`, `pg_postmaster_start_time()`, `pg_database` | head `0011_sessions_journeys`; postmaster started 2026-06-16; only `webchat_db` app DB | High |
| E5 | 2026-09-26 → 2026-09-28 | `journalctl -u webchat` grep `admin/invites` | bounded to 48h | `GET /api/admin/invites` → **200 OK** at 00:24:17 UTC 2026-09-28 (screenshot time); 401 only for my unauthenticated curl | High |
| E6 | 2026-09-28 00:31 | Public + host | `curl /admin/dashboard \| grep assets/index-`; grep `dist/index.html` | Served and on-disk index reference `index-CuA7AIXC.js` + `index-ZrVFgcNQ.css`; `dist/index.html` mtime 2026-09-22 22:11:36 | High |
| E7 | 2026-09-28 00:33 | Host `frontend/dist*` | grep each retained dir's index.html | `dist.rollback-04d34ce…` → `JNY7hdXb` (July 28 build); `dist.failed-841d8ae` → `CG3kTq87`; `CuA7AIXC.js` asset mtime 2026-07-04 22:40 | High |
| E8 | repo | git | `git show 90a176d:frontend/dist/index.html`; `git log -- frontend/dist/index.html` | Tracked index at `90a176d` references **`CuA7AIXC.js`**; the host's working copy is byte-identical to tracked HEAD (`git status` clean for that path) | High |
| E9 | repo | `.tmt-agent-deploy/config.yaml` release-staging rollback | step order | 1) `mv dist → dist.failed-841d8ae`; 2) `mv dist.rollback-90a176d → dist`; 3) **`git reset --hard 90a176d`** (overwrites tracked `dist/index.html`) | High |
| E10 | repo | git | `e914e6f:frontend/src/pages/AdminDashboard.tsx:55-57` vs `90a176d:…/AdminDashboard.tsx:60-61`; `90a176d:backend/routers/invites.py` `get_invites` | Old UI: `setInvites(response.data.invites \|\| [])`. The API returns `{items,total,accepted,pending}`, and the current UI reads `items` | High |
| E11 | 2026-09-28 00:34 | Host | test each asset referenced by `dist.rollback-04d34ce…/index.html` exists in `dist/assets` | `index-JNY7hdXb.js`, `index-B0sEkoZJ.css` present | High |
| E12 | 2026-09-28 00:34 | Host | `ls dist/static/feedback-summaries` | Absent from live `dist`. Whether the July 28 bundle expected it here is unknown | Medium |

## 4. Timeline

- 2026-07-04 22:40: the `CuA7AIXC` bundle is built, and the committed `frontend/dist/index.html` is last updated to point at it (commit `e914e6f`). (E7, E8)
- 2026-07-28 16:26: run `20260728T162622Z-production-4494a92` ships `90a176d` with the `JNY7hdXb` frontend via scp. Git's tracked index.html is **not** updated to match; it stays at `CuA7AIXC` in `90a176d`. (E7, E8, `state/MEMORY.md`)
- 2026-09-22 22:09: run `ee7fba5` retains the live dist as `dist.rollback-90a176d`, resets the tracked index, and pulls `841d8ae`. The disk preflight then fails. (E1, E9)
- 2026-09-22 22:11:36: the rollback moves the retained bundle back, then `git reset --hard 90a176d` overwrites `dist/index.html` with the stale tracked copy (`CuA7AIXC`). The service restarts at 22:11:39. `/health` gives 502 during startup and later 200. **Symptom starts.** (E1, E2, E6, E9)
- 2026-09-22 → 2026-09-26: the DB keeps receiving writes (chats, feedback cases). The API serves 200s. (E3, E5)
- 2026-09-28 00:24: the admin loads the dashboard; the API returns 200 with 65 invites and the UI shows 0. (E5, E10)

## 5. Reproduction or observable signature

- **Signature (safe, unauthenticated):** `curl -s https://alochat.platform.confabs.org/admin/dashboard | grep -o 'assets/index-[^"]*js'`
  - Failing: `assets/index-CuA7AIXC.js`. Expected for `90a176d`: `assets/index-JNY7hdXb.js`.
- **Data signature:** `docker exec webchat-db psql -U postgres -d webchat_db -Atc "select count(*) from invites"` → 65 (non-zero), while the UI shows 0.
- **Frequency:** deterministic, 100% since 2026-09-22 22:11:36 UTC.
- **Limitation:** I did not call the authenticated API with an admin token. That the API returned invites is inferred from the 200 status (E5) and the unscoped query (E10), not from inspecting a response body.

## 6. Hypothesis ledger

| Rank | Hypothesis and prediction | Probe | Evidence | Result | Status |
|---|---|---|---|---|---|
| 1 | Rollback left a stale frontend. Prediction: the served asset ≠ `JNY7hdXb` and the tracked index = the served index. | Compare the served, on-disk, tracked, and retained index.html files | E6, E7, E8, E9, E10 | Served `CuA7AIXC` = tracked `90a176d` index; the old UI reads `.invites` | **supported** |
| 2 | The DB was wiped or recreated (volume lost, container recreated, migration dropped data). Prediction: the tables would be empty or the container newly created. | Row counts, container age, postmaster start | E2, E3, E4 | 65 invites, 26 users, writes on 09-26; container up 3 months | **falsified** |
| 3 | The app points at a different or empty database (`.env` drift). Prediction: `DATABASE_URL` names another DB/host, or counts differ. | Sanitized `DATABASE_URL`; `pg_database` list | E2, E4 | `localhost:5432/webchat_db`, the only app DB, has data | **falsified** |
| 4 | The API errors and the UI swallows the error. Prediction: 5xx or 4xx on `/api/admin/invites` when the admin loads. | journal grep, bounded to 48h | E5 | 200 OK at the screenshot time | **falsified** |
| 5 | A failed migration or partial deploy of `841d8ae` changed the schema. Prediction: head ≠ `0011` or a changed venv. | `alembic_version`; run record | E1, E4 | Head `0011`; the run stopped before venv creation or migration | **falsified** |

## 7. Causal analysis

**Observed facts:** the DB is intact (E3, E4). The API returns 200 (E5). The served frontend is the July 4 bundle (E6), whose index.html is exactly what git tracks at `90a176d` (E8). The rollback restores dist *before* `git reset --hard` (E9). The old dashboard reads `response.data.invites`, but the API emits `items` (E10).

**Supported inference, the causal chain:**
1. The frontend is shipped by scp, but `frontend/dist/index.html` is also committed to git. The committed copy has been stale since 2026-07-04.
2. The deploy of `841d8ae` fails at the disk preflight, and the rollback runs.
3. The rollback restores the correct July 28 `dist` and *then* runs `git reset --hard 90a176d`. That rewrites the tracked `dist/index.html` to reference `index-CuA7AIXC.js`, a bundle file still on disk in `dist/assets`.
4. Browsers load the July 4 SPA. Its `AdminDashboard` calls `/api/admin/invites`, gets `{items: [...65]}`, reads `.invites`, which is `undefined`, and falls back to `[]`. The counts show 0 and it renders "No invites sent".

**Why the safeguards missed it:**
- Rollback verification checks only `/health` (E1). Only the forward post-install smoke checks the source-specific frontend asset, and it never ran.
- Earlier rollbacks (for example `fd26cb0`) show the same pattern: the `dist.rollback-65a091e` and `dist.failed-fd26cb0` copies both hold `CuA7AIXC`. This hazard has probably occurred before without being noticed (E7).
- The "reset generated frontend index before pull" step (E9) acknowledges the tracked-index conflict, but the rollback path does not compensate for it.

**Contributing factors:**
- Low disk (95%) triggered the rollback in the first place.
- Accumulated `dist.failed-*` and `dist.rollback-*` directories and old hashed assets also use disk.

**Unverified remainder:**
- Exactly which other pages are broken by the old UI.
- Whether `static/feedback-summaries/` (E12) should exist under the live `dist`.

## 8. Suggested fixes

- **F1 (required, operational; needs separate mutation authorization):** Restore the correct entry point by copying the retained July 28 index back into place: `cp dist.rollback-04d34ce…/index.html dist/index.html` on the host. Both referenced assets are already present (E11). Better still, re-ship `frontend/dist/.` built locally from `90a176d` via the reviewed scp step, which also restores any missing `static/feedback-summaries`. Risk: minimal, static-file only, no restart needed. Rollback path: copy the current `CuA7AIXC` index back.
- **F2 (required):** Reorder the release-staging rollback in `.tmt-agent-deploy/config.yaml` so that `git reset --hard <known-good>` runs **before** "restore known-good frontend bundle". Alternatively, re-copy `index.html` from the retained bundle after the reset. Alternative considered: dropping the reset. It ranks lower because the checkout must return to known-good code.
- **F3 (validation):** Add the source-specific frontend asset check to rollback verification. After rollback, the served `/` must reference the retained bundle's `index-*.js`, read from the retained `index.html` before restore. Use a delay or retry, as the forward smokes do, to avoid the 502 startup window.
- **F4 (hardening):** Stop tracking `frontend/dist/index.html` in git (`git rm --cached`, add it to `.gitignore`), since production ships dist by scp. This removes the root hazard, and with it the "reset generated index before pull" step. Compatibility: the Docker/dev flows must not depend on the committed dist; check `Dockerfile`, `Makefile`, and `DEPLOYMENT.md` at implementation time.
- **F5 (cleanup; destructive, separate authorization):** Prune old `frontend/dist.failed-*`, old `dist.rollback-*` dirs, and unreferenced hashed assets. Free disk to get above the 4 GiB preflight gate, possibly also via Docker image prune or journal vacuum. This is needed before `841d8ae` can deploy.

## 9. Implementation brief

### Objective
After any deploy rollback, production serves the retained known-good frontend bundle. Rollback verification fails loudly if it does not.

### Required changes
1. `.tmt-agent-deploy/config.yaml`, release-staging rollback: move `reset production code to known-good commit` before `restore known-good frontend bundle`. Keep `retain failed frontend bundle` first. Apply the same ordering to any other component rollback that touches `frontend/dist` and git (E9).
2. Same file, rollback verification: add a check that the public `/` `index-*.js` equals the retained bundle's entry, with retry and delay (E1, E6).
3. Repository: untrack `frontend/dist/index.html` and ignore `frontend/dist/`. Then remove the "reset generated frontend index before pull" step, and update `DEPLOYMENT.md` and `deploy.local.md` references (E8). This is discovery: confirm that no Docker or Make target reads the committed dist.
4. Refresh `.tmt-agent-deploy/state/artifacts.yaml` hashes and `state/MEMORY.md` to record the hazard and fix.

### Acceptance criteria
- A simulated rollback (non-prod or dry-run) leaves `dist/index.html` byte-identical to the retained bundle's `index.html`.
- Rollback verification fails when the served asset ≠ the retained asset.
- `git ls-files frontend/dist` is empty, and `git pull` on the host no longer conflicts with the shipped index.
- After F1, the admin dashboard on prod shows Total Invites = 65, the current DB count at restore time.

### Test plan
- Pre-fix failing assertion: run the rollback sequence against a scratch checkout where the tracked index differs from the retained bundle. The resulting index equals the tracked one (fail).
- Post-fix: the same scenario gives the retained index.
- Rehearse the config via the tmt-agent-deploy preflight/validation mode. Post-deploy observation: the E6 curl signature returns the expected hash.

### Non-goals
- Re-attempting the `841d8ae` deploy.
- Changing the API response shape.
- Adding backward-compatible `.invites` fields.
- Database work of any kind.

### Risks and constraints
- The config holds reviewed, hash-pinned artifacts. Config edits require re-review under tmt-agent-deploy.
- Untracking dist changes the developer workflow for anyone relying on a committed build.
- Disk is at 95%, so any re-ship must fit, since the assets are small.

### Implementation inputs
Run `20260922T220910Z-production-ee7fba5`; `DEPLOYMENT.md`; `deploy.local.md`; evidence E1–E12; retained good index `frontend/dist.rollback-04d34ceb63390448c29a9af2c802c2f703f22cbe/index.html` (sha256 prefix `912e7623477c1a8c`).

## 10. Open questions and blockers
- Should `static/feedback-summaries/` exist under the live `dist` (E12)? This decides whether F1 can be the single-file copy or needs a full re-ship. Owner: operator. Resolve by checking the `90a176d` build output locally.
- Disk remediation scope for F5. Owner: operator. Not blocking F1–F4.

## 11. Readiness and next authorization
**READY.** Next authorization requested: approve **F1**, restoring the correct frontend `index.html` on production. This is a mutation and is outside this read-only investigation.

## Addendum: F1 applied (2026-09-28 ~00:40 UTC, user-authorized)

- Backed up the stale entry point to `frontend/dist/index.html.stale-CuA7AIXC`, then copied `dist.rollback-04d34ce…/index.html` to `frontend/dist/index.html`. No restart.
- Verified: public `/admin/dashboard` now references `index-JNY7hdXb.js` + `index-B0sEkoZJ.css`; the asset returns 200; `/health` is healthy.
- E12 resolved: `feedback-summaries` does not exist in `90a176d` (it ships with `841d8ae`), so the single-file restore is complete.
- To undo: `cp dist/index.html.stale-CuA7AIXC dist/index.html`.
- Caveat: the next `git reset --hard` or `git checkout -- frontend/dist/index.html` on the host reintroduces the stale index until F2/F4 land.
