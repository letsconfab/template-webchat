# ADR-0006: Multi-session Chat management and curated Journeys

- **Date:** 2026-07-27
- **Status:** Accepted
- **Amends:** [ADR-0003](0003-authenticated-chat-session-ownership.md)

## Context

ADR-0003 established authenticated ownership of Chat Sessions but deferred
multi-session discovery and management. Negative-feedback evolution requires
durable, account-owned conversations with list/switch/New Chat/rename/delete,
plus administrator-curated starter Journeys.

## Decision

Ownership rules from ADR-0003 remain: a Chat Session belongs to one
authenticated tester; the client UUID is a locator only; quarantine and
collision behavior are unchanged.

In addition:

1. Testers may list, create, rename, and delete only their owned Chat Sessions
   through authenticated HTTP APIs.
2. Each Chat Session has a human-readable title and a stable `/chat/:uuid` URL.
3. Generation may use a bounded window of the *current* Chat Session's history
   only; content must not cross between sessions.
4. Start-screen Journeys are administrator-curated, ordered, and activated.
   Knowledge Sources support Journey content but do not auto-publish Journeys.

## Consequences

Clients replace single-`sessionStorage` resume with account-scoped session
lists while still authenticating WebSocket frames per ADR-0003. Schema gains
`chat_sessions.title` and a `journeys` table. Operators must run migration
`0011_sessions_journeys`.
