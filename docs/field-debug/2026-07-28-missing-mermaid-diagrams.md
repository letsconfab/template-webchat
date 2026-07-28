# Field debug: no Mermaid diagrams in chat responses

- Report timestamp: `2026-07-28T14:55:00Z`
- Implementation readiness: `READY`
- Severity: medium (answer-quality evolution gap; app otherwise healthy)
- Status: ongoing on production after successful release `04d34ce`; not a deploy/runtime outage
- Symptom: After the negative-feedback evolution deploy, structured answers (e.g. “What is the INTEGRATE framework?”) render as text lists/citations/follow-ups with **no Mermaid diagram** and no Mermaid fallback code block.
- Expected: For relationship / sequence / system-structure questions, the assistant may emit one small Mermaid fenced block that the shared `Markdown` component renders as SVG (with accessible text equivalent / code fallback).
- Environment / target / components: `production` / `webchat` / chat generation (`build_system_prompt`) → websocket stream persist → `ChatPage` `Markdown` / lazy `mermaid` renderer
- Deployed source: `04d34ceb63390448c29a9af2c802c2f703f22cbe` (run `20260728T000934Z-production-2e95256`; frontend asset `index-JNY7hdXb.js`; migration head `0011_sessions_journeys`)
- First known bad: `2026-07-28T13:07:25Z` (assistant message `232`, INTEGRATE answer post-deploy; no mermaid fence)
- Last known good: none for Mermaid emission (all-time mermaid fence count is `0`)
- Supported cause (confidence: **high**): diagrams are absent because the **model never emits ` ```mermaid ` fences**. The frontend Mermaid capability is live and unused. The system prompt only optionally mentions Mermaid, gives no fence example, and conflicts with “avoid large frameworks / no diagram by default for simple factual answers,” so structure questions stay as numbered lists.

## 2. Safety and target state

- Public `/health`: healthy (`{"status":"healthy"}`)
- Live SPA references `/assets/index-JNY7hdXb.js` (`200`); `mermaid.core-CjLeSFcc.js` (`200`); bundle contains Mermaid render strings
- Host HEAD: `04d34ce`; `webchat` `active`; local loopback health healthy
- No active deployment run (`.tmt-agent-deploy/state/current-run.yaml` absent; latest finalized run succeeded)
- Blast radius: visual answer-quality only; citations, follow-ups, sessions/journeys, auth, and health unaffected
- Data integrity: unaffected (no corruption; messages stored without Mermaid fences)
- Rollback / emergency action: **not required**; do not roll back `04d34ce` for this gap
- Constraints honored: read-only probes only (public curl, SSH status/file reads, sanitized SQL aggregates/flags). No deploys, restarts, flag changes, data mutation, or product-code edits.

Note on “preview deployment”: this repository’s harness defines only `production`. The successful post-evolution release the screenshots exercise is production run `20260728T000934Z-production-2e95256`.

## 3. Evidence index

| ID | UTC timestamp/window | Source | Sanitized query or reference | Observation | Reliability |
|---|---|---|---|---|---|
| E1 | 2026-07-28T00:09:34Z | `.tmt-agent-deploy/runs/20260728T000934Z-production-2e95256.md` | deploy summary | Release `04d34ce` / asset `index-JNY7hdXb.js` / migration `0011` succeeded; smoke health + asset + API 401 | high |
| E2 | 2026-07-28T00:06–00:15Z | `.tmt-agent-deploy/state/MEMORY.md` | live release notes | Live SHA `04d34ce`; prior known-good `9ab280c`; frontend asset `index-JNY7hdXb.js` | high |
| E3 | 2026-07-28T14:50Z | public curl | `GET /health`; `GET /assets/index-JNY7hdXb.js`; `GET /assets/mermaid.core-CjLeSFcc.js` | healthy; JS `200` (~1.05MB); mermaid core `200` (~611KB); main bundle includes `mermaid` / `Rendering diagram` | high |
| E4 | 2026-07-28T14:50Z | SSH host | `git rev-parse HEAD`; `index.html` asset ref; `systemctl is-active webchat` | HEAD `04d34ce`; SPA → `index-JNY7hdXb.js`; `mermaid.core-CjLeSFcc.js` present; `active` | high |
| E5 | 2026-07-28T14:50Z | SSH + deployed source | `backend/services/chat_generation.py` on host | Prompt contains Mermaid sentence; **` ```mermaid ` example absent** | high |
| E6 | 2026-07-28T14:51Z | SQL read-only | all-time assistant fence aggregates | `120` assistant msgs; `4` any triple-backtick fence; `0` word `mermaid`; `0` ` ```mermaid ` fences | high |
| E7 | 2026-07-28T14:51Z | SQL read-only | INTEGRATE assistant msgs since `2026-07-28` | ids `232` (`13:07:25Z`, len 1611) and `240` (`14:45:45Z`, len 1742): `mermaid_fence=no`, `any_fence=no`, `word_mermaid=no` | high |
| E8 | 2026-07-28 ~14:47 local | user screenshots | INTEGRATE chat UI | Structured text + sources + follow-ups; no SVG diagram; no “Rendering diagram…”; no Mermaid fallback fence | high |
| E9 | repo `main` @ `04d34ce` | `frontend/src/components/Markdown.tsx` + `Markdown.test.tsx` | MermaidBlock + unit tests | FE renders `language-mermaid` fences when present; fallback on render failure | high |
| E10 | repo | `backend/services/chat_generation.py` + `tests/test_chat_generation.py` + `tests/test_negative_feedback_regression.py` | prompt + regression | Diagram guidance is optional one-liner; tests only `assertIn("Mermaid", prompt)`; no fence-syntax or structure-trigger contract | high |
| E11 | repo | `docs/evolution/2026-07-27-negative-feedback-evolution.md` Decision 2 | optional diagram policy | Diagrams optional; must not replace text; simple factual answers should not acquire diagrams by default | high |

## 4. Timeline

- **Pre-evolution:** shared Markdown had no Mermaid renderer (evolution brief called this out). [E11]
- **2026-07-27–28:** PR #16 / commit `04d34ce` adds FE Mermaid rendering + optional prompt sentence; shipped in production run `20260728T000934Z-production-2e95256`. [E1][E2][E9][E10]
- **2026-07-28T00:14Z:** Live assets `index-JNY7hdXb.js` / `mermaid.core-*.js` present and publicly served. [E1][E3][E4]
- **2026-07-28T13:07:25Z:** Assistant message `232` answers INTEGRATE with structured Markdown; no Mermaid fence stored. [E7][E8]
- **2026-07-28T14:45:45Z:** Another INTEGRATE-related assistant message `240` likewise has no Mermaid fence. [E7]
- **2026-07-28T14:50–14:55Z:** Field probes confirm healthy deploy, live Mermaid assets, zero all-time Mermaid emissions. [E3][E4][E5][E6]

## 5. Reproduction or observable signature

- **Deployed-path signature:** Persist/stream an assistant answer to a structure/framework question; stored `chat_messages.content` lacks ` ```mermaid `; UI shows no Mermaid SVG / “Rendering diagram…” / Mermaid fallback.
- **Safe observation used:** sanitized SQL flags on existing INTEGRATE messages `232`/`240` + all-time fence counts (no new chat traffic generated).
- **Expected failing result:** `mermaid_fence=no` despite structure content suitable for a diagram.
- **Observed:** `mermaid_fence=no` for both INTEGRATE answers; all-time Mermaid fence count `0`. [E6][E7][E8]
- **Frequency:** consistent (no Mermaid emissions observed in the entire message history).
- **Baseline:** frontend unit tests prove rendering works when a fence is supplied; production asset includes Mermaid. [E3][E9]
- **Limitations:** no authenticated live chat probe was issued (would create tenant traffic). Stored-message absence is sufficient to discriminate generation vs render failure.

## 6. Hypothesis ledger

| Rank | Hypothesis and prediction | Probe | Evidence | Result | Status |
|---|---|---|---|---|---|
| H1 | Generation never emits Mermaid fences (prompt too weak/conflicting; no fence example). Prediction: DB has `0` ` ```mermaid ` rows; INTEGRATE answers have structured lists only | SQL fence counts + prompt inspection | E5–E8, E10–E11 | `0` all-time Mermaid fences; INTEGRATE msgs fence-free; prompt optional + no example | **supported** |
| H2 | Frontend Mermaid renderer missing/broken on live asset. Prediction: live bundle lacks Mermaid chunks / `Markdown` path unused | Public + host asset probes; code review | E3, E4, E9 | Mermaid assets `200`; bundle strings present; ChatPage uses `Markdown` | **falsified** |
| H3 | Pipeline strips or mutates Mermaid fences before persist/UI. Prediction: fences appear transiently or other fences are stripped | SQL any-fence counts; `extract_followups` review | E6, E10 | Follow-up strip only removes `:::followups`; other fences can persist (4 historical plain fences); no Mermaid ever present to strip | **falsified** |
| H4 | Deploy did not ship Mermaid-capable frontend / wrong SHA. Prediction: live SHA or asset predates Mermaid work | Deploy run + HEAD + index ref | E1–E4 | Live `04d34ce` / `index-JNY7hdXb.js` with Mermaid core | **falsified** |
| H5 | Mermaid render fails client-side so only raw fence should show. Prediction: screenshots/DB show ` ```mermaid ` source or “could not be rendered” fallback | Screenshots + SQL | E7, E8 | Neither fence nor fallback UI present | **falsified** |

## 7. Causal analysis

### Observed facts

- Production on `04d34ce` is healthy and serving a Mermaid-capable SPA. [E1][E3][E4]
- Chat UI renders assistant content through `Markdown`, which special-cases `language-mermaid`. [E9]
- System prompt tells the model it *may* include a Mermaid diagram, but provides no fence syntax example and pairs that with “simple factual answers should not acquire a diagram by default” plus “avoid large frameworks … unless requested.” [E5][E10][E11]
- Zero assistant messages in the database contain a Mermaid fence; INTEGRATE answers that users saw as diagram-worthy contain none. [E6][E7][E8]
- Automated regression only asserts the substring `Mermaid` appears in the prompt. [E10]

### Supported inference

The user-visible gap is **generation non-emission**, not missing frontend capability. For framework/sequence questions, the model follows the stronger brevity / anti-framework / “optional diagram” cues and answers with numbered lists. Because no ` ```mermaid ` block is produced, the Mermaid renderer never activates.

### Unverified remainder

- Exact model/provider sampling behavior for a hardened prompt (needs non-prod generation rehearsal after prompt change).
- Whether product intent is “should usually diagram structure questions” vs “remain rare/optional”; evolution text supports optional-but-expected-when-clearer-visually.

### Why preflight/smoke missed it

Release smokes check health, asset HTTP 200, and API 401 only. [E1] They do not assert Mermaid emission or render on a structure question. Unit coverage stops at “prompt mentions Mermaid” and “Markdown can render a supplied fence.”

## 8. Suggested fixes

1. **`required` — Strengthen the diagram generation contract** in `backend/services/chat_generation.py` (`build_system_prompt`):
   - Keep one small diagram max and keep text-first.
   - Explicitly require a Mermaid fence when the answer explains a multi-part framework, process/sequence, or system relationship (e.g. INTEGRATE elements / change-process steps).
   - Include a minimal ` ```mermaid ` … ` ``` ` example (flowchart/sequence) so the model knows the exact fence form.
   - Resolve the conflict with “avoid large frameworks” by clarifying that a compact diagram is allowed/expected for framework overviews even when large tables are not.
   - Evidence addressed: E5–E8, E10–E11.
   - Alternatives ranked lower: frontend-only heuristics (cannot invent diagrams without model content); forcing diagrams for every answer (violates brevity contract).

2. **`validation` — Extend regression/contract tests**:
   - `tests/test_chat_generation.py` / `tests/test_negative_feedback_regression.py`: assert fence example + structure-trigger language exist in the prompt.
   - Keep/extend `Markdown.test.tsx` (already covers render + fallback).
   - Add a focused non-live fixture or eval note for structure prompts expecting a Mermaid fence once generation is exercised in staging/rehearsal.

3. **`hardening` — Optional post-deploy smoke observation**:
   - Document a manual or harness-safe check: structure question → stored content contains ` ```mermaid ` → UI shows SVG (or accessible fallback), without authorizing production mutation here.

4. **`cleanup`:** None.

Risks: stronger diagram guidance may slightly increase answer length or occasional invalid Mermaid (FE already falls back to source). Rollback is prompt/test revert; no schema/data migration.

## 9. Implementation brief

### Objective

Structure/framework/sequence answers on production should include one Mermaid fenced diagram that renders in chat (or shows the accessible code fallback), while preserving concise text-first answers and existing citation/follow-up behavior.

### Required changes

1. Update `build_system_prompt` in `backend/services/chat_generation.py` per fix #1 (structure-trigger rule + fence example + conflict clarification). Evidence: E5, E10, E11.
2. Update prompt-contract unit/regression tests in `tests/test_chat_generation.py` and `tests/test_negative_feedback_regression.py` so Mermaid is covered beyond a bare substring check. Evidence: E10.
3. Implementation-time discovery only if needed: confirm websocket persist path still stores fences unchanged (already indicated by historical non-Mermaid fences; E6). No FE change required unless discovery finds a new strip path.

### Acceptance criteria

- Prompt contains an explicit ` ```mermaid ` example and a clear rule to emit one diagram for multi-part framework / sequence / relationship answers.
- Prompt still forbids replacing the textual answer with a diagram-only reply and still caps diagrams at one.
- For a local/non-prod rehearsal of an INTEGRATE-style question, assistant content includes a Mermaid fence OR a documented model refusal path is not the default.
- Existing Markdown Mermaid unit tests remain green.
- Citations, follow-ups, and brevity contract keywords remain present.
- No requirement to change production data.

### Test plan

- Pre-fix failing assertion: regression/unit checks that require ` ```mermaid ` example / structure-trigger language currently fail on today’s prompt.
- Focused tests: prompt contract + existing `Markdown.test.tsx`.
- Integration: optional local chat against a structure question; assert stored/streamed content contains a Mermaid fence (live LLM; environment-dependent).
- Full suite: existing backend/frontend unit suites.
- Non-production rehearsal + post-deploy smoke observation (not authorized by this report): ask a framework question; confirm fence in response and SVG/fallback in UI.

### Non-goals

- Rolling back `04d34ce`
- Reworking citation/follow-up UX
- Making every factual answer include a diagram
- Changing Mermaid securityLevel / theme unless render bugs appear after emission starts
- Production instrumentation or DB backfill

### Risks and constraints

- LLM nondeterminism: prompt hardening raises emission rate but does not guarantee 100% compliance without eval gates.
- Invalid Mermaid syntax must remain safe via existing fallback.
- Keep answers concise; diagram must stay small.

### Implementation inputs

- Source identity: `04d34ce` / run `20260728T000934Z-production-2e95256` / asset `index-JNY7hdXb.js`
- Files: `backend/services/chat_generation.py`, `tests/test_chat_generation.py`, `tests/test_negative_feedback_regression.py`, `frontend/src/components/Markdown.tsx` (reference only), evolution Decision 2
- Evidence IDs: E1–E11
- Safe reuse commands: public `/health` + asset curls; sanitized SQL fence counts using `chr(96)` concatenation (avoid shell backtick breakage)

## 10. Open questions and blockers

None for implementation of the prompt/contract fix.

## 11. Readiness and next authorization

Verdict: **READY**

Next authorization requested: **implementation** of the required prompt + test changes (separate from any deploy authorization).
