# WebChat Domain

This repository has one bounded context: authenticated testers use a grounded
assistant, and administrators operate the assistant and respond to reported
answer-quality problems.

## Ubiquitous language

### Chat Session

An ordered conversation between one authenticated tester and the assistant. A
Chat Session belongs to exactly one tester. Its browser-generated identifier
locates it but does not prove ownership.

### Feedback Case

A durable report created from a tester's negative rating of one assistant
answer. A Feedback Case stays connected to the rated exchange and its Chat
Session, has an opaque public identifier, and records which party is expected
to respond.

### Feedback Summary

A version-controlled, privacy-reviewed Markdown report of aggregate themes from
negative feedback over a fixed evidence window (currently 30 days). Feedback
Summaries are authored outside the deployed runtime, packaged into the frontend
at build time, and shown to administrators above the Feedback Case list. They
are not Feedback Cases, do not query production feedback at page load, and are
not stored in the application database.

### Feedback Summary Artifact

The canonical Markdown file under `docs/feedback-summaries/` that defines one
Feedback Summary. It carries YAML front matter (`artifact_id`, evidence window,
authoring workflow, `privacy_reviewed`) and required body sections. The build
packages derived static files from these artifacts; the Markdown in Git remains
canonical.

### Case Reply

An immutable, chronological message added to a Feedback Case by its tester or
an administrator. A correction is another Case Reply; an existing reply is
never edited or deleted.

### Conversation Replay

The complete chronological view of the Chat Session containing a rated answer.
The tester sees their original conversation. Administrators see only the
privacy-safe projection approved for administrative review.

### Execution Trace

A bounded, sanitized record of operational events produced while generating an
assistant answer. It supports diagnosis without retaining model reasoning,
secrets, raw tool payloads, or retrieved passages.

### Knowledge Source

An administrator-controlled document in the indexed ALO corpus (typically a
read-only Google Drive file). Retrieval returns passage text with provenance:
document title, canonical Google URL, revision metadata, and the finest honest
locator available (for example a Markdown heading or chunk index).

### Journey

An administrator-curated starter path on the chat start screen. A Journey has a
short title, plain-language purpose, one vetted starter prompt, optional icon,
display order, active/inactive state, and an explicit connection to the
Knowledge Sources that support it. Knowledge Sources do not automatically
create or publish Journeys.

