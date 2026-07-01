# ADR-0004: Separate owner content from fail-closed admin projections

- **Date:** 2026-07-01
- **Status:** Accepted

## Context

Conversation Replay is useful to administrators but contains tester-supplied
and assistant-echoed personal information. Owners need their original
conversation, while administrative diagnosis does not justify unrestricted
raw access. On-demand redaction that falls back to raw text on failure would
turn an operational error into a privacy breach.

## Decision

Persist raw user-derived content for its authenticated owner separately from a
cached, versioned administrative projection. User messages, assistant
messages, feedback comments, source labels, and user Case Replies each record
projection status as `pending`, `succeeded`, or `failed`.

Generate projections locally under Python 3.11 with structured recognizers and
English named-entity recognition for people and locations. Do not send content
to an LLM for redaction.

Administrative APIs return only a projection whose version is current and
status is `succeeded`. Pending, failed, unavailable, or stale projections
return an unavailable marker and never raw content. Account emails use an
approved masked representation. Admin-authored Case Replies remain visible to
the case owner.

## Consequences

Owner and administrator representations intentionally differ. Redaction
failures reduce diagnostic visibility instead of confidentiality. Backfill and
readiness tooling must expose pending and failed counts, and admin replay
cannot be enabled while eligible projections remain pending. Projection schema
or recognizer changes require a new version and reprocessing.

