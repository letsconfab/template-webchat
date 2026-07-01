# ADR-0003: Authenticated Chat Session ownership

- **Date:** 2026-07-01
- **Status:** Accepted

## Context

The browser creates a UUID for a conversation and previously used that value as
both locator and authority. Anyone able to present another UUID could request
its history. Future Feedback Cases and replay require a durable, defensible
ownership boundary.

## Decision

A Chat Session belongs to one authenticated user. The browser sends its current
JWT in the first WebSocket frame. The server validates the token and active
user before reading configuration, loading history, binding a session, or
persisting a message.

A UUID is an opaque locator only. First use atomically creates and binds the
Chat Session to the authenticated user. Later use succeeds only for that owner.
Missing or invalid authentication and ownership collisions use stable
application close codes without revealing whether another user's session
exists.

Existing HTTP history and clear operations must enforce the same ownership
rule or be removed. Multi-session discovery and management are not introduced
by this decision.

Legacy ownership is inferred only when all linked feedback identifies the same
user. Ambiguous, conflicting, and ownerless sessions are quarantined and
cannot be replayed.

## Consequences

Reconnection preserves an owned conversation and supports Feedback Case
authorization. Browser clients must authenticate immediately after connection.
The database needs an atomic uniqueness boundary for the UUID and an explicit
ownership/quarantine state. Legacy anonymous sessions may become unavailable
rather than being assigned on weak evidence.

