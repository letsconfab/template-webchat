# Webchat Evolution Brief: 30-Day Negative Feedback

Status: Grilling complete; approved evolution direction  
Prepared: 2026-07-27  
Evidence window: rolling 30 days ending 2026-07-27 (UTC)

## Grilling decision log

### Decision 1: Sequence the evolution around answer quality and trust

Status: Accepted on 2026-07-27

The next evolution will be an answer-quality and trust release before it
becomes a broader capability release.

The sequence is:

1. pass relevant conversation history into generation;
2. introduce concise, progressive answers and clarification behavior;
3. require visible evidence for ALO-specific, policy, licensing, and IP claims;
4. add durable session navigation and guided ALO journeys; and
5. defer file upload until its privacy, retention, authorization, and IP
   boundaries are defined.

### Decision 2: Use a concise, progressive first-response contract

Status: Accepted on 2026-07-27

The default first response will:

1. give the direct answer first, targeting 120–180 words;
2. provide no more than three actionable steps;
3. avoid large frameworks and tables unless requested;
4. offer one optional path to go deeper; and
5. ask one clarifying question instead of answering when the prompt is
   ambiguous, lacks essential context, or concerns an unsupported ALO-specific
   policy or IP claim.

The contract can expand when the tester explicitly requests detail.

The response may also include one small Markdown or Mermaid diagram when a
relationship, sequence, or system structure is materially clearer visually.
The diagram is optional, follows the initial direct answer, and must not replace
the concise textual explanation. Simple factual answers should not acquire a
diagram by default.

The current shared Markdown component supports GitHub-flavored Markdown but
does not render Mermaid. Mermaid support is therefore an explicit frontend
capability in this evolution, including safe rendering, an accessible text
equivalent, and a readable code-block fallback if rendering fails.

### Decision 3: Apply a three-tier evidence and citation policy

Status: Accepted on 2026-07-27

Claims fall into three evidence classes:

1. **ALO evidence required:** ALO frameworks, definitions, metrics, history,
   governance, programs, policies, licensing, and IP claims must be supported
   by retrieved ALO Knowledge Source material.
2. **General guidance allowed:** General coaching, facilitation, and
   organizational-development guidance may be answered without an ALO source
   when it is clearly labeled as general guidance.
3. **Clarify or decline:** The assistant must clarify or decline when an
   ALO-specific claim has no supporting source, terminology is ambiguous,
   sources conflict, or the request crosses into legal advice.

If ALO evidence is missing, the assistant says so. It may offer general
guidance only after making that boundary explicit and obtaining the tester's
consent.

ALO citations must be as precise as the source format allows and must link back
to the original read-only Google document in the Knowledge Source. The
presentation contract is:

- place a citation next to the claim it supports;
- show the human-readable document title;
- include the most precise honest locator available, such as heading, section,
  page, slide, sheet and range, or stable chunk/paragraph label;
- link to the canonical read-only Google document;
- never invent a fine-grained locator when only document-level provenance is
  available; and
- retain enough revision metadata to diagnose a citation against the indexed
  version when the Google document later changes.

Meeting this contract requires indexing changes. The current Drive cache keeps
the Google file ID in a local sidecar, but the vector payload exposes only a
filename and chunk text. It does not preserve the canonical Google URL, MIME
type, revision or modified time, chunk index, heading, page, slide, sheet range,
or another fine-grained locator.

### Decision 4: Use durable, account-owned, session-isolated conversations

Status: Accepted on 2026-07-27

Chat Sessions will be durable resources owned by the authenticated tester and
available across that tester's devices.

The tester experience will include:

- a stable URL for each conversation;
- an automatically generated title, optional rename, and last-updated time;
- a conversation list with New Chat, switch, and confirmed delete actions; and
- reliable restoration of the selected conversation rather than dependence on
  one browser's `sessionStorage`.

Each conversation is an isolated context. Generation may use a bounded form of
the current conversation's history, summarizing older content when necessary,
but it will not silently read or remember content from the tester's other
conversations.

### Decision 5: Make all starter journeys administrator-curated

Status: Accepted on 2026-07-27

The start screen will show only administrator-curated journeys. The knowledge
base may support a journey's content, but it will not automatically decide
which journeys the product promotes.

Each journey will have:

- a short title and plain-language purpose;
- one vetted starter prompt;
- an optional icon or small diagram;
- an administrator-controlled display order and active/inactive state; and
- an explicit connection to the ALO Knowledge Sources that support it.

Usage and feedback may inform administrator revisions, but they do not
automatically publish or reorder journeys.

### Decision 6: Generate constrained, tester-reviewed follow-ups

Status: Accepted on 2026-07-27

After a grounded answer, the assistant may offer up to three follow-up
questions. Suggestions will:

- derive only from the current conversation, active starter journey, and cited
  Knowledge Sources;
- prefer one deeper exploration and one or two adjacent supported directions;
- be suppressed when evidence or confidence is insufficient;
- avoid unrelated general-purpose tasks; and
- enter the message composer for tester review rather than sending
  automatically.

### Decision 7: Defer file upload

Status: Deferred on 2026-07-27

File upload is not part of the current evolution. It remains recorded as a
future enhancement because testers expressed a document-review need, but no
upload, parsing, storage, retention, authorization, deletion, or shared
Knowledge Source behavior will be planned in the current release.

When the enhancement is reconsidered, the product must first resolve whether
attachments are temporary or durable, conversation- or account-scoped, and
private analysis material or candidates for administrator-controlled Knowledge
Source promotion.

### Decision 8: Use the existing Feedback system without redesigning it

Status: Confirmed out of scope on 2026-07-27

The Feedback system is already implemented and is the evidence and measurement
surface for this evolution. Sparse categories, comments, and unresolved case
statuses are observations about the analyzed sample, not authorization or a
requirement to redesign feedback capture, case states, correspondence, or
resolution behavior.

### Decision 9: Gate completion on regression, grounding, and behavior evidence

Status: Accepted on 2026-07-27

The answer-quality and trust horizon is complete when:

1. all critical cases applicable to that horizon in the eleven-feedback
   regression set pass;
2. ALO factual claims have valid, precise Knowledge Source links and no
   unsupported assertions;
3. at least 90% of evaluated answers follow the concise first-response
   contract;
4. ambiguous prompts consistently trigger clarification;
5. current-conversation history demonstrably improves follow-up answers without
   content crossing between separate Chat Sessions; and
6. the release is observed through the existing Feedback system for 30 days.

Because current usage volume is small, the production observation evaluates
whether negative themes recur rather than treating a raw percentage as
statistically conclusive.

## Purpose

This brief turns the deployed webchat's recent negative feedback into a product
evolution direction. It is intentionally not a detailed implementation plan.
Its product choices were resolved through a one-question-at-a-time grilling
session and are ready to be translated into a detailed implementation plan.

## Executive summary

The deployed webchat is functioning mechanically, but it is not yet shaping the
conversation around the tester's intent.

The dominant evolution need is to move from a single, mostly blank chat surface
that often gives a large, confident answer into a guided, persistent,
evidence-disciplined assistant that:

1. starts with a concise and actionable answer;
2. deepens only when the tester asks;
3. asks for clarification rather than confidently expanding an ambiguous
   prompt;
4. preserves and exposes past conversations;
5. guides testers toward supported ALO journeys and useful next questions; and
6. makes the evidence boundary visible for ALO-specific, policy, licensing, and
   IP claims.

File upload is a real requested capability, but it should follow explicit
decisions about privacy, retention, knowledge-base scope, and ALO intellectual
property.

## Evidence base and limitations

The analysis used production `UserFeedback`, `FeedbackCase`, Chat Session,
privacy-redacted Conversation Replay, and sanitized Execution Trace data. No
tester identity is included in this document.

### Usage and feedback baseline

| Measure | Result |
|---|---:|
| Active testers | 6 |
| Active Chat Sessions | 11 |
| Assistant answers | 60 |
| Submitted ratings | 13 |
| Thumbs down | 11 |
| Thumbs up | 2 |
| Testers who submitted a thumbs down | 3 |
| Sessions represented by negative feedback | 5 |
| Negative items with a written comment | 6 |
| Negative items with at least one selected category | 4 |

Directional ratios:

- 11 negative ratings represent 18.3% of the 60 assistant answers in the
  window. This is not a true dissatisfaction rate because rating is optional
  and self-selected.
- 84.6% of submitted ratings were negative. This is useful as a feedback-loop
  signal, not a population estimate.
- Feedback is concentrated: the three negative-feedback testers submitted 5,
  4, and 2 items respectively.
- Ten of the eleven negatively rated turns performed a knowledge retrieval;
  all ten completed successfully and returned source identifiers. The remaining
  turn did not require retrieval. All eleven traces completed without an
  operational error.
- Negatively rated answers averaged 3,278 characters versus 2,281 across all
  assistant answers. The positive sample is too small to infer a general
  length-to-satisfaction relationship.

### Data-quality caveats

- Seven of eleven negative items have no selected category.
- Five have no written comment.
- Two are bare thumbs-down reports with neither category nor comment.
- A feedback row records creation time but not the time of a later vote change,
  so the window is based on the available `created_at` field.
- Several themes below are inferred from the redacted rated exchange. Inferred
  findings are labeled as such.

## Complete negative-feedback inventory

The inventory below accounts for all eleven negative ratings without exposing
tester-identifying or raw conversation content.

| ID | Date | High-level signal | Primary theme |
|---|---|---|---|
| NF-01 | Jul 4 | Answer was incomplete despite being long; tester asked for more actionable tasks | Progressive, actionable answers |
| NF-02 | Jul 14 | Explicitly marked off-topic, outdated, and too long | Relevance, freshness, and brevity |
| NF-03 | Jul 14 | Past chats did not appear accessible; requested a left navigation and delete control | Conversation persistence and navigation |
| NF-04 | Jul 14 | Blank start state was confusing; requested an index or suggested ALO topics | Guided discovery |
| NF-05 | Jul 14 | Requested clickable suggested next questions after an answer | Guided continuation |
| NF-06 | Jul 14 | Requested direct file upload for reviewing documents and policies | Document workflow |
| NF-07 | Jul 14 | IP-protection question received a negative rating after an answer containing strong policy/licensing assertions | Trust and evidence boundaries |
| NF-08 | Jul 17 | Bare thumbs down after a very short or ambiguous prompt produced a confident domain answer; no reason was supplied | Clarification behavior (inferred) |
| NF-09 | Jul 17 | Explicitly marked too long | Brevity and progressive disclosure |
| NF-10 | Jul 17 | Tester asked for a simpler starting point because prior material was confusing; answer was marked off-topic | Intent and cognitive-load adaptation |
| NF-11 | Jul 17 | Bare thumbs down on a multi-part answer; subsequent case handling identified verbosity as the likely issue | Progressive disclosure (inferred) |

## What the feedback says at a high level

### 1. The assistant does not reliably adapt depth to the tester

Four items primarily concern answer shape and cognitive load. The issue is not
simply character count: testers want a small, useful first step, an actionable
baseline, and the option to go deeper. Long frameworks and tables can be useful,
but they should not be the automatic first response, especially after a tester
says the material is confusing.

Desired evolution:

- Lead with the direct answer and one to three next actions.
- Use progressive disclosure: brief answer, optional deeper explanation,
  examples, or framework.
- Detect explicit cues such as "too confusing," "where do I begin," and "too
  much information."
- Prefer a clarifying question when the request is ambiguous or the appropriate
  depth is uncertain.
- Offer a visible response-depth control only if prompt-based adaptation proves
  insufficient.

### 2. Retrieval success is not the same as a grounded, trustworthy answer

Two items directly raise relevance, freshness, or trust concerns, and one bare
thumbs down appears to involve ambiguity handling. The negative turns did not
show tool failures: retrieval completed and returned sources. This points toward
source relevance, synthesis, claim discipline, or response framing rather than
basic retrieval availability.

The IP case is the clearest risk. Organization-specific licensing and
governance claims should not be stated as settled facts unless the retrieved
material supports them and the answer shows that provenance.

Desired evolution:

- Treat ALO-specific, policy, licensing, and IP questions as evidence-required.
- Show source citations or a compact "based on" section for factual claims.
- Distinguish retrieved fact, model inference, and missing evidence.
- Ask for clarification on acronyms and short ambiguous prompts.
- Do not silently fall back to general model knowledge for organization-specific
  claims.
- Evaluate retrieval relevance and answer faithfulness, not just whether the
  retrieval tool returned results.

### 3. The product feels like one ephemeral conversation

Three items ask for conversation continuity or guidance: visible history,
starter journeys, and suggested follow-ups. These are related needs. Testers do
not only want storage; they want orientation before a conversation, a visible
place to return to it, and help choosing the next useful step.

The current application persists Chat Sessions, but the browser holds one
session UUID in `sessionStorage`. There is no tester-facing session list,
switcher, title, explicit New Chat action, or delete endpoint. The empty state
contains only a generic instruction to type a message.

Desired evolution:

- Add a tester-owned conversation list with titles, recency, switch, New Chat,
  and delete.
- Make the current session addressable and recoverable across browser sessions
  and devices.
- Add a curated start screen organized around supported ALO journeys.
- Add evidence-grounded suggested follow-up questions after an answer.
- Ensure suggestions stay within the assistant's supported domain instead of
  encouraging arbitrary general-purpose use.

### 4. Document review is desired, but its boundary is undecided

One item explicitly requests chat file upload. This could materially improve
policy and document-review workflows, but "upload" can mean several different
products:

- temporary one-turn attachment;
- private per-tester document workspace;
- ingestion into a shared organizational knowledge base; or
- an administrator-curated source pipeline.

Those options have different retention, authorization, deletion, prompt
injection, copyright, and ALO IP implications. The evolution should not treat
them as interchangeable.

Recommended starting direction:

- Defer implementation until the intended upload scope and retention model are
  chosen.
- If prioritized, begin with temporary, owner-scoped attachments that are not
  added to the shared knowledge base by default.

### 5. The existing Feedback system is the measurement surface

At the time of analysis, five cases were awaiting administrator action and six
were awaiting tester action; none of the eleven was resolved. Only four items
used a category, partly because the current taxonomy describes answer failures
but not product or workflow requests.

These are analysis limitations, not current product requirements. The Feedback
system is already implemented and will be used without redesign to measure the
answer-quality, trust, and conversation-experience changes in this evolution.

## Code-confirmed product constraints

These constraints are relevant to the feedback and should be accounted for in
the eventual plan:

1. Chat history is stored server-side, but only the browser's current
   `sessionStorage` UUID is resumed.
2. There is no user-facing API or UI to list, title, switch, create explicitly,
   or delete Chat Sessions.
3. The empty chat state has no domain journeys or starter prompts.
4. The chat input accepts text only.
5. The system prompt asks the model to be concise but does not define
   progressive disclosure, ambiguity handling, or evidence-required claim
   classes.
6. When retrieval returns no result, the current prompt allows an answer from
   general model knowledge, including for potentially organization-specific
   questions.
7. Stored history is displayed to the tester, but the current agent invocation
   sends only the latest user message to the model. Multi-turn continuity can
   therefore appear in the UI without informing the next generated answer.
8. The shared chat and replay Markdown component supports GitHub-flavored
   Markdown but has no Mermaid renderer.
9. Retrieval results expose a filename and passage text, but not the canonical
   Google document URL or a precise section/page/slide/range locator. Source
   provenance must be carried from Drive sync through chunking, vector storage,
   retrieval, generation, execution traces, and chat rendering.

## Proposed evolution sequence

This sequence is a recommendation to test in the grilling session.

### Horizon 1: Answer quality and trust

- Pass relevant conversation history into generation.
- Introduce concise-first, progressive answer behavior.
- Add ambiguity detection and clarifying questions.
- Require grounded evidence and visible provenance for ALO-specific and
  policy/IP claims.
- Preserve canonical Google document links, revisions, and the finest
  source-format locator available in every indexed chunk.
- Render claim-level citations that open the read-only Google Knowledge Source.
- Add optional, safely rendered Mermaid diagrams with an accessible text
  equivalent and code-block fallback.
- Build a small regression set from the eleven negative cases.

### Horizon 2: Guided, durable conversations

- Add session list, titles, New Chat, switch, resume, and delete.
- Replace the blank state with curated ALO journeys and starter prompts.
- Add grounded suggested next questions.

### Future enhancement: Bounded document workflows

File upload is explicitly out of scope for the current evolution. If
reprioritized later, decide attachment scope, retention, authorization,
deletion, security controls, and Knowledge Source ingestion rules before
planning implementation.

### Cross-cutting: Measure through the existing Feedback system

- Use the implemented ratings, categories, comments, Feedback Cases, and
  Conversation Replay without changing their current product contract.
- Measure whether each evolution reduces the corresponding negative theme.

## Outcomes to measure

The detailed plan should choose targets only after confirming expected usage
volume and acceptable sample sizes. Candidate measures are:

- negative ratings per rated answer and per assistant answer;
- rate of `too_long`, `off_topic`, `outdated`, and unsupported-claim reports;
- percentage of negative ratings with a usable reason;
- task-success evaluation on the eleven-case regression set;
- grounded-claim precision and citation coverage for ALO-specific answers;
- citation-link validity and locator precision against the indexed Google
  source revision;
- clarification rate and success on ambiguous prompts;
- median first-answer length, segmented by intent rather than globally;
- starter-journey and suggested-follow-up engagement;
- returning testers who reopen a prior Chat Session.

## Decisions for the grilling session

Resolve these dependencies one at a time:

1. **Resolved:** The next evolution is primarily an answer-quality and trust
   release; broader capabilities follow.
2. **Resolved:** The first response gives a direct 120–180-word answer, at most
   three actions, one optional deeper path, and a clarifying question when
   essential context or evidence is missing. One small Markdown or Mermaid
   diagram may follow when it materially improves understanding.
3. **Resolved:** ALO claims require precise, claim-level citations to the
   original read-only Google Knowledge Source; general guidance is labeled;
   unsupported, ambiguous, conflicting, or legal claims are clarified or
   declined.
4. **Resolved:** Conversations are durable, account-owned, available across
   devices, and isolated from one another. The selected conversation supplies
   bounded history to generation and supports list, title, rename, New Chat,
   switch, and confirmed delete actions.
5. **Resolved:** All start-screen journeys are administrator-curated, ordered,
   and activated. Knowledge Sources support their content but do not
   automatically create or publish journeys.
6. **Resolved:** Follow-ups are generated but constrained to the current
   conversation, active journey, and cited sources. Up to three are shown only
   when supported and enter the composer for tester review.
7. **Deferred:** File upload is a future enhancement and is out of scope for
   this evolution. Its ownership, retention, deletion, security, and Knowledge
   Source rules remain intentionally unresolved.
8. **Out of scope:** The Feedback system is already implemented and will be
   used as the measurement surface without redesign.
9. **Resolved:** Completion requires all applicable critical regression cases,
   precise and valid ALO citations with no unsupported assertions, at least 90%
   first-response-contract adherence, consistent ambiguity clarification,
   verified session-isolated history use, and a 30-day qualitative production
   observation.
