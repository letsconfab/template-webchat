# ADR-0001: Migrate from `create_react_agent` to `create_agent`

- **Date:** 2026-06-29
- **Status:** Proposed

## Context

The chat backend currently constructs its tool-calling agent with
`langgraph.prebuilt.create_react_agent`. LangChain v1 replaced this pre-v1
helper with `langchain.agents.create_agent`.

The application already depends on LangChain 1.x, so retaining the older
LangGraph helper increases upgrade risk and keeps the chat path on a superseded
API. The existing behavior remains appropriate: one model, an optional
knowledge-retrieval tool, a system prompt, and a streamed event loop.

## Decision

Replace:

```python
from langgraph.prebuilt import create_react_agent
```

with:

```python
from langchain.agents import create_agent
```

Construct the agent with the equivalent LangChain v1 interface:

```python
agent = create_agent(
    model=llm,
    tools=tools,
    system_prompt=_build_system_prompt(
        has_kb=len(tools) > 0,
        provider=getattr(llm, "model", "unknown"),
        model=getattr(llm, "model_name", "unknown"),
    ),
)
```

The migration must preserve:

- conditional exposure of the `retrieve_knowledge` tool;
- the existing system-prompt behavior;
- the `start`, `think`, `chunk`, and `end` WebSocket protocol;
- bounded graph execution through the recursion limit;
- response aggregation, error handling, and message persistence.

No retrieval, prompt, or product behavior changes are part of this decision.

## Consequences

The chat path will use LangChain's supported v1 agent API and follow its current
upgrade path. The primary migration risk is event-stream compatibility:
`astream_events` event names and payloads consumed by the WebSocket adapter must
be verified against `create_agent`.

Implementation requires focused tests for:

- agent construction with and without the retrieval tool;
- model-token and tool lifecycle event translation;
- recursion-limit and error behavior;
- the WebSocket frame sequence and persisted assistant response.

The migration is complete only when these behaviors match the current
implementation.

## Reference

- [LangChain v1 migration guide](https://docs.langchain.com/oss/python/migrate/langchain-v1)
