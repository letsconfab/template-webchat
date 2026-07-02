# Domain Docs

This is a single-context repository. Engineering skills should use the root
domain glossary and architectural decisions.

## Before exploring

- Read `CONTEXT.md` at the repository root when it exists.
- Read relevant decisions under `docs/adr/`.
- If `CONTEXT.md` does not exist, proceed silently. Domain-modeling workflows
  create it lazily when terminology is resolved.

## Vocabulary

Use canonical terms from `CONTEXT.md` in issue titles, design proposals, tests,
and implementation. If a needed concept is missing, either reconsider the term
or record the gap for a domain-modeling session.

## Architectural decisions

Surface conflicts with an existing ADR explicitly instead of silently
overriding the recorded decision.
