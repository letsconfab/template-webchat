"""Blank assistant answers after retrieval must not be stored as success.

Field debug 2026-09-22: sarvam-105b can stream a long reasoning trace and only
a leading newline on the answer channel. That newline is not an answer.
"""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from backend.llm_providers import SarvamLLM
from backend.main import _query_with_knowledge


RETRIEVAL_TEXT = "ALO licensing policy requires a written application."
USER_QUESTION = "How do I license ALO?"
REASONING = "private chain of thought that must stay off the answer"
RETRY_REASONING = "retry reasoning that must not be stored"
ASSISTANT_ANSWER = "File the license form."


class _Chunk:
    def __init__(self, content: str = "", reasoning: str = "") -> None:
        self.content = content
        self.additional_kwargs = (
            {"reasoning_content": reasoning} if reasoning else {}
        )


class _FakeAgent:
    def __init__(self, events: list[dict]) -> None:
        self.events = events
        self.stream_calls = 0

    async def astream_events(self, payload, version="v2", config=None):
        self.stream_calls += 1
        for event in self.events:
            yield event


class _FakeStream:
    def __init__(self, lines: list[str], payloads: list[dict], payload: dict) -> None:
        self.status_code = 200
        self._lines = lines
        self._payloads = payloads
        self._payload = payload

    async def __aenter__(self):
        self._payloads.append(self._payload)
        return self

    async def __aexit__(self, *args):
        return False

    def aiter_lines(self):
        async def _lines():
            for line in self._lines:
                yield line

        return _lines()

    async def aread(self):
        return b""


class _FakeClient:
    def __init__(self, lines: list[str], payloads: list[dict]) -> None:
        self._lines = lines
        self._payloads = payloads

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def stream(self, method, url, headers=None, json=None, timeout=None):
        return _FakeStream(self._lines, self._payloads, json)


def _sse(delta: dict) -> str:
    return "data: " + json.dumps({"choices": [{"delta": delta}]})


def _retrieval_events(answer: str, transcript: list | None = None) -> list[dict]:
    messages = transcript if transcript is not None else [
        HumanMessage(content=USER_QUESTION),
        ToolMessage(content=RETRIEVAL_TEXT, tool_call_id="call-1"),
        AIMessage(content=answer),
    ]
    return [
        {
            "event": "on_chat_model_stream",
            "data": {"chunk": _Chunk(reasoning=REASONING)},
        },
        {
            "event": "on_tool_start",
            "name": "retrieve_knowledge",
            "run_id": "run-1",
            "data": {"input": {"query": "license"}},
        },
        {
            "event": "on_tool_end",
            "name": "retrieve_knowledge",
            "run_id": "run-1",
            "data": {"output": RETRIEVAL_TEXT},
        },
        {
            "event": "on_chat_model_stream",
            "data": {"chunk": _Chunk(content=answer)},
        },
        {
            "event": "on_chain_end",
            "name": "LangGraph",
            "data": {
                "output": {
                    "messages": messages
                }
            },
        },
    ]


class BlankAssistantAnswerTests(unittest.IsolatedAsyncioTestCase):
    async def _run_turn(self, answer: str, lines: list[str], agent=None):
        payloads: list[dict] = []
        stored: dict = {}
        traces: list[dict] = []
        sent: list[dict] = []
        agent = agent or _FakeAgent(_retrieval_events(answer))

        async def persist_message(*, chat_session, role, content, metadata=None):
            stored.update(role=role, content=content, metadata=metadata)
            return 262

        async def persist_trace(message_id, events):
            traces.append({"message_id": message_id, "events": events})

        class WebSocket:
            async def send_json(self, payload):
                sent.append(payload)

        def client_factory(*args, **kwargs):
            return _FakeClient(lines, payloads)

        with (
            patch(
                "backend.main.graphrag_service.is_ready",
                new=AsyncMock(return_value=False),
            ),
            patch("langgraph.prebuilt.create_react_agent", return_value=agent),
            patch("backend.main._persist_chat_message", new=persist_message),
            patch("backend.main._persist_execution_trace", new=persist_trace),
            patch("backend.llm_providers.httpx.AsyncClient", client_factory),
        ):
            await _query_with_knowledge(
                SarvamLLM(api_key="test-key-1234567890", model="sarvam-105b"),
                USER_QUESTION,
                [],
                SimpleNamespace(id=51, client_uuid="session-51"),
                WebSocket(),
                provider="sarvam",
                model="sarvam-105b",
            )

        return stored, traces, sent, payloads, agent

    async def test_newline_only_completion_stores_followup_not_the_newline(self) -> None:
        lines = [
            _sse({"reasoning_content": RETRY_REASONING}),
            _sse({"content": ASSISTANT_ANSWER}),
            "data: [DONE]",
        ]
        stored, traces, sent, payloads, agent = await self._run_turn("\n", lines)

        self.assertEqual(stored["content"], ASSISTANT_ANSWER)
        self.assertNotIn(REASONING, stored["content"])
        self.assertNotIn(RETRY_REASONING, stored["content"])
        self.assertFalse(stored["metadata"]["error"])
        self.assertEqual(agent.stream_calls, 1)
        self.assertEqual(len(payloads), 1)
        body = payloads[0]
        self.assertIsNone(body["reasoning_effort"])
        self.assertIn('"reasoning_effort": null', json.dumps(body))
        self.assertEqual(body["max_tokens"], 2048)
        joined = "\n".join(message["content"] for message in body["messages"])
        self.assertIn(USER_QUESTION, joined)
        self.assertIn(RETRIEVAL_TEXT, joined)
        self.assertNotIn(RETRY_REASONING, joined)
        self.assertFalse(any(message["content"] == "\n" for message in body["messages"]))
        end = next(frame for frame in sent if frame["type"] == "end")
        self.assertEqual(end["content"], ASSISTANT_ANSWER)
        self.assertEqual(traces[0]["message_id"], 262)
        self.assertIn(
            "tool_completed",
            [event["event_type"] for event in traces[0]["events"]],
        )

    async def test_blank_followup_stores_visible_error(self) -> None:
        lines = [
            _sse({"reasoning_content": RETRY_REASONING}),
            _sse({"content": "\n"}),
            "data: [DONE]",
        ]
        stored, traces, sent, payloads, agent = await self._run_turn("\n", lines)

        self.assertEqual(
            stored["content"],
            "The assistant didn't return an answer. Please try again.",
        )
        self.assertNotEqual(stored["content"].strip(), "")
        self.assertNotIn(REASONING, stored["content"])
        self.assertNotIn(RETRY_REASONING, stored["content"])
        self.assertTrue(stored["metadata"]["error"])
        self.assertEqual(len(payloads), 1)
        self.assertIsNone(payloads[0]["reasoning_effort"])
        self.assertEqual(payloads[0]["max_tokens"], 2048)
        self.assertEqual(agent.stream_calls, 1)
        end = next(frame for frame in sent if frame["type"] == "end")
        self.assertEqual(end["content"], stored["content"])
        self.assertIn(
            "tool_completed",
            [event["event_type"] for event in traces[0]["events"]],
        )

    async def test_newline_followed_by_letters_is_stored_without_retry(self) -> None:
        answer = "\nThe license form is required."
        stored, traces, sent, payloads, agent = await self._run_turn(answer, [])

        self.assertEqual(stored["content"], answer)
        self.assertFalse(stored["metadata"]["error"])
        self.assertEqual(payloads, [])
        self.assertEqual(agent.stream_calls, 1)
        end = next(frame for frame in sent if frame["type"] == "end")
        self.assertEqual(end["content"], answer)
        self.assertNotIn(REASONING, stored["content"])
        self.assertIn(
            "tool_completed",
            [event["event_type"] for event in traces[0]["events"]],
        )

    async def test_followup_suggestions_stay_on_an_assistant_answer(self) -> None:
        answer = (
            "Here is the answer.\n\n"
            ":::followups\n"
            "- How does licensing work?\n"
            ":::\n"
        )
        stored, _traces, sent, payloads, _agent = await self._run_turn(answer, [])

        self.assertEqual(stored["content"], "Here is the answer.")
        self.assertEqual(
            stored["metadata"]["followups"],
            ["How does licensing work?"],
        )
        self.assertFalse(stored["metadata"]["error"])
        self.assertEqual(payloads, [])
        end = next(frame for frame in sent if frame["type"] == "end")
        self.assertEqual(end["content"], "Here is the answer.")
        self.assertEqual(end["followups"], ["How does licensing work?"])

    async def test_stream_error_after_newline_does_not_store_the_newline(self) -> None:
        class FailingAgent(_FakeAgent):
            async def astream_events(self, payload, version="v2", config=None):
                self.stream_calls += 1
                for event in self.events:
                    yield event
                raise RuntimeError("agent blew up")

        agent = FailingAgent(_retrieval_events("\n"))
        stored, _traces, sent, payloads, _agent = await self._run_turn(
            "\n", [], agent=agent
        )

        self.assertEqual(stored["content"], "An error occurred: agent blew up")
        self.assertTrue(stored["metadata"]["error"])
        self.assertEqual(payloads, [])
        end = next(frame for frame in sent if frame["type"] == "end")
        self.assertEqual(end["content"], "An error occurred: agent blew up")

    async def test_followup_keeps_question_when_chain_end_is_only_the_blank_answer(
        self,
    ) -> None:
        lines = [
            _sse({"content": ASSISTANT_ANSWER}),
            "data: [DONE]",
        ]
        agent = _FakeAgent(
            _retrieval_events("\n", transcript=[AIMessage(content="\n")])
        )
        stored, _traces, _sent, payloads, _agent = await self._run_turn(
            "\n", lines, agent=agent
        )

        self.assertEqual(stored["content"], ASSISTANT_ANSWER)
        joined = "\n".join(message["content"] for message in payloads[0]["messages"])
        self.assertIn(USER_QUESTION, joined)
        self.assertIn(RETRIEVAL_TEXT, joined)


class OrdinarySarvamStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_ordinary_stream_leaves_reasoning_enabled(self) -> None:
        payloads: list[dict] = []
        lines = [
            _sse({"reasoning_content": REASONING, "content": ASSISTANT_ANSWER}),
            "data: [DONE]",
        ]

        def client_factory(*args, **kwargs):
            return _FakeClient(lines, payloads)

        llm = SarvamLLM(api_key="test-key-1234567890", model="sarvam-105b")
        with patch("backend.llm_providers.httpx.AsyncClient", client_factory):
            chunks = [
                chunk
                async for chunk in llm.astream([HumanMessage(content=USER_QUESTION)])
            ]

        self.assertEqual(len(payloads), 1)
        self.assertNotIn("reasoning_effort", payloads[0])
        self.assertNotIn("max_tokens", payloads[0])
        self.assertEqual(chunks[0].content, ASSISTANT_ANSWER)
        self.assertEqual(chunks[0].additional_kwargs["reasoning_content"], REASONING)


if __name__ == "__main__":
    unittest.main()
