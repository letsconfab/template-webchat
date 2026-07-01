# ADR-0002: Persist sanitized agent execution traces

- **Date:** 2026-07-01
- **Status:** Accepted

## Context

The chat backend emits `think` WebSocket frames for model-reasoning fragments
and tool lifecycle events. These frames are transient. The persisted assistant
message contains only the final answer and metadata such as `thought_count`,
provider, model, duration, and error status.

User feedback links to the persisted assistant message, so reviewers cannot
determine which tools ran, which sources informed the answer, or whether a tool
failed. Persisting raw `think` frames would expose model reasoning and may also
retain sensitive tool inputs or retrieved content. Raw reasoning is not required
to evaluate retrieval quality or diagnose execution failures.

## Decision

Persist a structured, sanitized execution trace associated with each assistant
chat message. Keep the existing `think` frames as an ephemeral presentation
channel; they are not the persistence format.

Each trace uses a schema version and contains at most 100 ordered events and
64 KiB of serialized data. Each persisted event contains only reviewable
operational data:

- event sequence and timestamp;
- event type, such as `tool_started`, `tool_completed`, or `tool_failed`;
- tool name and execution duration;
- success or failure status with a safe error category;
- locally redacted source identifiers or citations used by retrieval;
- result count and an approved, bounded summary when needed.

Do not persist:

- raw model reasoning or chain-of-thought;
- complete tool inputs or outputs;
- credentials, tokens, or provider payloads;
- retrieved document text already available through its source identifier;
- unsanitized exception messages.

Collect sanitized events during the agent turn and persist them after the
assistant message has an ID. Truncation and capture failure are explicit states
and must not interrupt chat streaming. Historical messages have no synthesized
trace and are shown as `trace not captured`.

Only administrative review APIs may return traces, after all user-derived
fields have crossed the fail-closed projection in ADR-0004. Apply retention,
redaction, and size limits independently from WebSocket frame limits.

## Consequences

Feedback reviewers will be able to evaluate retrieval behavior and execution
failures without receiving private model reasoning or full knowledge-base
content. Trace data will have stable application semantics even if LangGraph
event payloads change.

This adds a persistence schema, event sanitization logic, authorization checks,
and retention requirements. A failure before the assistant message is created
leaves no trace.

Implementation requires tests that verify:

- event ordering and association with the correct assistant message;
- redaction of secrets, raw reasoning, tool inputs, and retrieved text;
- bounded summaries and trace sizes;
- reviewer authorization;
- useful traces for successful, failed, and partially completed tool calls.
