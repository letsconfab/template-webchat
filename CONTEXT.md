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

