# WebChat Domain

This repository has one bounded context: authenticated members use a grounded
assistant, and administrators operate the assistant and respond to reported
answer-quality problems.

## Ubiquitous language

### Member

A non-administrator person signed in to the app on behalf of A Loving
Organization: ALO staff, board members, and invited participants. Every
non-administrator user is a Member.
_Avoid_: Tester (the pilot-era name; it survives only in older code identifiers
such as `tester_correspondence_enabled`), user, end user

### Chat Session

An ordered conversation between one authenticated member and the assistant. A
Chat Session belongs to exactly one member. Its browser-generated identifier
locates it but does not prove ownership.

### Feedback Case

A durable report created from a member's negative rating of one assistant
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

An immutable, chronological message added to a Feedback Case by its member or
an administrator. A correction is another Case Reply; an existing reply is
never edited or deleted.

### Conversation Replay

The complete chronological view of the Chat Session containing a rated answer.
The member sees their original conversation. Administrators see only the
privacy-safe projection approved for administrative review.

### Execution Trace

A bounded, sanitized record of operational events produced while generating an
assistant answer. It supports diagnosis without retaining model reasoning,
secrets, raw tool payloads, or retrieved passages.

### Knowledge Source

An administrator-controlled document in the indexed ALO corpus (typically a
read-only Google Drive file). Where a Library Manifest is configured, the
Knowledge Sources are exactly its Library Documents and Reference Documents. Retrieval returns passage text with provenance:
document title, canonical Google URL, revision metadata, and the finest honest
locator available (for example a Markdown heading or chunk index).

### Loving System in Practice

A published case study of one organization's loving systems, written by A
Loving Organization. Abbreviated LSP.
_Avoid_: case study (on its own)

### INTEGRATE System

One of the nine systems of A Loving Organization's INTEGRATE framework:
Inspire, Nurture, Trust, Embody, Guide, Regulate, Align, Transcend, Engage.
ALO's own sheets are authoritative for this vocabulary.
_Avoid_: INTEGRATE domain, domain

### Spotlight

An INTEGRATE System that a Loving System in Practice features in full
narrative. Each LSP spotlights a small fixed number of Systems (currently
three), even though its text may touch others.

### Library Document

A document that the Library Manifest includes and that Members can browse and
open in the Resource Library. It appears under every INTEGRATE System it
spotlights.

### Library Manifest

The curator-maintained list that defines the Resource Library: which exact
document versions are included, their member-facing titles, and their
Spotlights. It lists both Library Documents and Reference Documents.
Inclusion in the Library Manifest is what approval means; filename markers
such as "APP" are not.

### Reference Document

A document that the Library Manifest includes for the Librarian to draw on
but that does not appear when browsing the Resource Library, such as the
Consortium Charter or the INTEGRATE Playbook.

### Librarian

The assistant Members talk to. It answers only from Library Documents and
Reference Documents, and otherwise asks a clarifying question or declines.
_Avoid_: chatbot, AI assistant (in member-facing language)

### Journey

An administrator-curated starter path on the chat start screen. A Journey has a
short title, plain-language purpose, one vetted starter prompt, optional icon,
display order, active/inactive state, and an explicit connection to the
Knowledge Sources that support it. Knowledge Sources do not automatically
create or publish Journeys.

