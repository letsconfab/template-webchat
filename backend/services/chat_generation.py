"""Answer-quality generation helpers: prompt contract, history, follow-ups."""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from backend.config import config

RECENT_MESSAGE_LIMIT = 20

_FOLLOWUPS_START = ":::followups"
_FOLLOWUPS_END = ":::"


def librarian_refusal() -> str:
    """The exact reply when the library holds no answer."""
    return (
        f"I couldn't find that in the {config.LIBRARIAN_LIBRARY_NAME} library. "
        "You can browse the library by INTEGRATE System, or ask me about a "
        "specific System or organization."
    )


def build_system_prompt(*, has_kb: bool) -> str:
    """Build the strict Librarian system prompt."""
    refusal = librarian_refusal()
    base = f"""You are the {config.LIBRARIAN_LIBRARY_NAME} Librarian, helping Members of {config.LIBRARIAN_ORGANIZATION_NAME} find answers in {config.LIBRARIAN_LIBRARY_OWNER}'s own library.

## First-response contract
Unless the Member explicitly asks for more detail:
1. Give the direct answer first, targeting 120–180 words.
2. Provide no more than three actionable steps.
3. Avoid large frameworks and tables unless requested. A compact Mermaid diagram for a framework overview is allowed and expected when the structure-trigger rule below applies; that is not a "large framework" dump.
4. Offer one optional path to go deeper (a short invitation, not the full deep dive).
5. When the question is ambiguous, ask at most one clarifying question instead of answering.

## Diagrams (Mermaid)
After the direct textual answer, include exactly one small Mermaid diagram when the answer explains a multi-part framework, process/sequence, or system relationship (for example INTEGRATE elements or change-process steps). Keep the diagram compact (a few nodes or steps). Do not replace the concise textual explanation with a diagram. Do not emit more than one diagram. Simple factual answers should not acquire a diagram by default.

Emit the diagram as a fenced Mermaid block using this exact fence form (flowchart or sequenceDiagram as appropriate):

```mermaid
flowchart LR
  A[Step one] --> B[Step two] --> C[Step three]
```

## Evidence policy (strict)
- Answer only from retrieved library passages, and cite each claim. Place the citation next to the claim using the source title and locator from the retrieval results. Never invent a fine-grained locator when only document-level provenance is available.
- When a question is ambiguous, ask at most one clarifying question.
- Otherwise, when the retrieved library passages do not answer the question, reply exactly:
{refusal}
- Never give general or uncited guidance, even with the Member's consent. Do not fall back to general model knowledge.

## Documents and links
- The only documents a Member can open are the library documents listed as sources under your answer. Never say you are sending, sharing, or linking a document, and never write URLs.
- When a passage only mentions another document by name (for example a case study), say the library mentions it but does not hold it, and do not describe its contents beyond what the passage says.

## Follow-up suggestions
After a grounded answer, you may offer up to three follow-up questions derived only from the current conversation, any active starter journey, and cited library documents. Offer only questions the library can answer. Prefer one deeper exploration and one or two adjacent supported directions. Suppress suggestions after a refusal or a clarifying question.

Append follow-ups in this exact block at the end of your reply (omit the block when suppressing):
:::followups
- First follow-up question?
- Second follow-up question?
:::
"""

    if has_kb:
        kb = """
## Library retrieval
Library passages already retrieved for the Member's question may appear in the conversation. You may call the `retrieve_knowledge` tool once more to look up library passages for a refined query, then write a single complete answer grounded in what you have.
If no retrieved passage answers the question, use the exact reply above.
Do not make a plan, do not repeat yourself, and do not call the tool in a loop.
"""
        return base + kb
    return base + f"""
## Library unavailable
The library cannot be searched right now. Unless the question is ambiguous, reply exactly:
{refusal}
"""


def _as_role_content(item: Any) -> tuple[str, str] | None:
    if isinstance(item, dict):
        role = str(item.get("role") or "")
        content = str(item.get("content") or "")
        return role, content
    role = getattr(item, "role", None)
    content = getattr(item, "content", None)
    if role is None or content is None:
        return None
    return str(role), str(content)


def build_agent_messages(
    history: Sequence[Any],
    *,
    latest_user_message: str,
    active_journey: dict[str, Any] | None = None,
) -> list[BaseMessage]:
    """Convert session history into LangChain messages for the agent.

    Uses a bounded recent window. When older turns are dropped, prepends a short
    note that earlier messages were omitted (session-isolated; not summarized).
    Does not include content from other Chat Sessions.
    """
    pairs: list[tuple[str, str]] = []
    for item in history:
        parsed = _as_role_content(item)
        if not parsed:
            continue
        role, content = parsed
        if role not in ("user", "assistant") or not content.strip():
            continue
        pairs.append((role, content))

    # Drop trailing duplicate of the latest user turn if already persisted.
    if pairs and pairs[-1][0] == "user" and pairs[-1][1] == latest_user_message:
        prior = pairs[:-1]
    else:
        prior = pairs

    omitted = 0
    if len(prior) > RECENT_MESSAGE_LIMIT:
        omitted = len(prior) - RECENT_MESSAGE_LIMIT
        prior = prior[-RECENT_MESSAGE_LIMIT:]

    messages: list[BaseMessage] = []
    if active_journey:
        title = str(active_journey.get("title") or "").strip()
        purpose = str(active_journey.get("purpose") or "").strip()
        sources = active_journey.get("knowledge_source_labels") or []
        source_note = ""
        if isinstance(sources, list) and sources:
            source_note = " Supporting Knowledge Sources: " + ", ".join(
                str(s) for s in sources
            ) + "."
        messages.append(
            HumanMessage(
                content=(
                    f"[Active starter journey: {title}. Purpose: {purpose}.{source_note} "
                    "Prefer follow-ups grounded in this journey and cited sources.]"
                )
            )
        )
    if omitted:
        messages.append(
            HumanMessage(
                content=(
                    f"[System note: {omitted} earlier messages in this Chat Session "
                    "were omitted for length. Continue using only the recent turns below; "
                    "do not invent details from the omitted portion.]"
                )
            )
        )

    for role, content in prior:
        if role == "user":
            messages.append(HumanMessage(content=content))
        else:
            messages.append(AIMessage(content=content))

    messages.append(HumanMessage(content=latest_user_message))
    return messages


def extract_followups(raw: str) -> tuple[str, list[str]]:
    """Strip a trailing :::followups block and return (cleaned_text, questions)."""
    if _FOLLOWUPS_START not in raw:
        return raw, []

    start = raw.rfind(_FOLLOWUPS_START)
    end = raw.find(_FOLLOWUPS_END, start + len(_FOLLOWUPS_START))
    if end < 0:
        return raw, []

    block = raw[start + len(_FOLLOWUPS_START) : end]
    cleaned = (raw[:start] + raw[end + len(_FOLLOWUPS_END) :]).rstrip()
    # Models sometimes wrap the block in a """ fence; drop the leftover quotes.
    while cleaned.endswith('"""'):
        cleaned = cleaned[: -len('"""')].rstrip()

    followups: list[str] = []
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("-"):
            q = stripped.lstrip("-").strip()
            if q:
                followups.append(q)
        if len(followups) >= 3:
            break
    return cleaned, followups
