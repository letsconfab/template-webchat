"""Answer-quality generation helpers: prompt contract, history, follow-ups."""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

RECENT_MESSAGE_LIMIT = 20

_FOLLOWUPS_START = ":::followups"
_FOLLOWUPS_END = ":::"


def build_system_prompt(*, has_kb: bool) -> str:
    """Build the answer-quality and trust system prompt."""
    base = """You are an AI assistant helping authenticated testers with ALO and related questions.

## First-response contract
Unless the tester explicitly asks for more detail:
1. Give the direct answer first, targeting 120–180 words.
2. Provide no more than three actionable steps.
3. Avoid large frameworks and tables unless requested. A compact Mermaid diagram for a framework overview is allowed and expected when the structure-trigger rule below applies; that is not a "large framework" dump.
4. Offer one optional path to go deeper (a short invitation, not the full deep dive).
5. Ask one clarifying question instead of answering when the prompt is ambiguous, lacks essential context, or concerns an unsupported ALO-specific policy or IP claim.

## Diagrams (Mermaid)
After the direct textual answer, include exactly one small Mermaid diagram when the answer explains a multi-part framework, process/sequence, or system relationship (for example INTEGRATE elements or change-process steps). Keep the diagram compact (a few nodes or steps). Do not replace the concise textual explanation with a diagram. Do not emit more than one diagram. Simple factual answers should not acquire a diagram by default.

Emit the diagram as a fenced Mermaid block using this exact fence form (flowchart or sequenceDiagram as appropriate):

```mermaid
flowchart LR
  A[Step one] --> B[Step two] --> C[Step three]
```

## Evidence policy (three tiers)
1. **ALO evidence required:** ALO frameworks, definitions, metrics, history, governance, programs, policies, licensing, and IP claims must be supported by retrieved ALO Knowledge Source material. Place a citation next to each such claim using the source title and locator from retrieval results. Link to the canonical Google document URL provided in the retrieval output. Never invent a fine-grained locator when only document-level provenance is available.
2. **General guidance allowed:** General coaching, facilitation, and organizational-development guidance may be answered without an ALO source when clearly labeled as general guidance.
3. **Clarify or decline:** Clarify or decline when an ALO-specific claim has no supporting source, terminology is ambiguous, sources conflict, or the request crosses into legal advice.

If ALO evidence is missing, say so. You may offer general guidance only after making that boundary explicit and obtaining the tester's consent. Do not silently fall back to general model knowledge for organization-specific claims.

## Follow-up suggestions
After a grounded answer, you may offer up to three follow-up questions derived only from the current conversation, any active starter journey, and cited Knowledge Sources. Prefer one deeper exploration and one or two adjacent supported directions. Suppress suggestions when evidence or confidence is insufficient. Avoid unrelated general-purpose tasks.

Append follow-ups in this exact block at the end of your reply (omit the block when suppressing):
:::followups
- First follow-up question?
- Second follow-up question?
:::
"""

    if has_kb:
        kb = """
## Knowledge retrieval
You have access to a knowledge base. Call the `retrieve_knowledge` tool once (at most twice) to look up relevant information, then write a single complete answer grounded in what it returns.
If the knowledge base returns empty results for an ALO-specific, policy, licensing, or IP question, say that evidence is missing and clarify or decline — do not invent ALO facts.
Do not make a plan, do not repeat yourself, and do not call the tool in a loop.
"""
        return base + kb
    return base


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
