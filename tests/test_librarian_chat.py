"""A chat turn behaves as the strict Librarian (model and retriever stubbed)."""

from __future__ import annotations

import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage

from backend.config import config
from backend.main import _query_with_knowledge, graphrag_service
from backend.services import library
from backend.services.chat_generation import librarian_refusal

QUESTION = "How do teams build trust?"
ANSWER = "Teams build trust through repair [Practice One]."


def _doc(file_id: str, title: str, systems: list[str], doc_type: str = "LSP") -> dict:
    return {
        "file_id": file_id,
        "title": title,
        "organization": "Example Org",
        "type": doc_type,
        "systems": systems,
        "modified_time": "2026-10-01T00:00:00Z",
        "pdf_path": f"/srv/{file_id}.pdf",
        "cache_path": f"/kb_cache/library/{file_id}_{title}.txt",
        "status": "ok",
    }


def _hit(text: str, file_id: str, filename: str) -> dict:
    return {
        "score": 0.8,
        "payload": {"text": text, "filename": filename, "google_file_id": file_id, "chunk_index": 0},
    }


class _Chunk:
    def __init__(self, content: str) -> None:
        self.content = content
        self.additional_kwargs = {}


class _FakeAgent:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.inputs: list = []

    async def astream_events(self, payload, version="v2", config=None):
        self.inputs.append(payload)
        yield {"event": "on_chat_model_stream", "data": {"chunk": _Chunk(self.answer)}}
        yield {
            "event": "on_chain_end",
            "name": "LangGraph",
            "data": {"output": {"messages": [*payload["messages"], AIMessage(content=self.answer)]}},
        }


class LibrarianChatTurnTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = patch.object(config, "LIBRARY_FILES_DIR", self.tmp.name)
        patcher.start()
        self.addCleanup(patcher.stop)
        library.write_library({
            "documents": [
                _doc("lib_1", "Practice One", ["trust", "engage"]),
                _doc("ref_1", "Charter", [], doc_type="Reference"),
            ],
            "issues": [],
        })

    async def _turn(self, hits: list[dict], agent: _FakeAgent):
        stored: dict = {}
        sent: list[dict] = []
        traces: list = []

        async def persist_message(*, chat_session, role, content, metadata=None):
            stored.update(role=role, content=content, metadata=metadata)
            return 7

        async def persist_trace(message_id, events):
            traces.append(events)

        class WebSocket:
            async def send_json(self, payload):
                sent.append(payload)

        create_agent = MagicMock(return_value=agent)
        with (
            patch.object(graphrag_service, "is_ready", new=AsyncMock(return_value=True)),
            patch.object(graphrag_service, "qdrant_ready", new=AsyncMock(return_value=True)),
            patch.object(graphrag_service, "_embed_query", new=AsyncMock(return_value=[0.1])),
            patch.object(graphrag_service, "_search_qdrant", new=AsyncMock(return_value=hits)),
            patch("langgraph.prebuilt.create_react_agent", create_agent),
            patch("backend.main._persist_chat_message", new=persist_message),
            patch("backend.main._persist_execution_trace", new=persist_trace),
        ):
            await _query_with_knowledge(
                MagicMock(),
                QUESTION,
                [],
                SimpleNamespace(id=3, client_uuid="session-3"),
                WebSocket(),
            )
        return stored, sent, traces, create_agent

    async def test_only_library_and_reference_passages_reach_the_model(self) -> None:
        agent = _FakeAgent(ANSWER)
        stored, sent, traces, _ = await self._turn(
            [
                _hit("LIBRARY PASSAGE", "lib_1", "lib_1_Practice One.txt"),
                _hit("REFERENCE PASSAGE", "ref_1", "ref_1_Charter.txt"),
                _hit("UNKNOWN PASSAGE", "zzz_9", "zzz_9_Other.txt"),
            ],
            agent,
        )

        model_input = "\n".join(str(m.content) for m in agent.inputs[0]["messages"])
        self.assertIn("LIBRARY PASSAGE", model_input)
        self.assertIn("REFERENCE PASSAGE", model_input)
        self.assertNotIn("UNKNOWN PASSAGE", model_input)
        self.assertEqual(agent.inputs[0]["messages"][-1].content, QUESTION)
        self.assertEqual(stored["content"], ANSWER)

        end = next(frame for frame in sent if frame["type"] == "end")
        self.assertEqual(
            end["citations"],
            [
                {"id": "lib_1", "title": "Practice One", "type": "LSP", "systems": ["trust", "engage"], "url": "/api/library/documents/lib_1/file"},
                {"id": "ref_1", "title": "Charter", "type": "Reference", "systems": [], "url": "/api/library/documents/ref_1/file"},
            ],
        )
        self.assertEqual(stored["metadata"]["citations"], end["citations"])
        trace_text = str(traces)
        self.assertNotIn("LIBRARY PASSAGE", trace_text)

    async def test_no_corpus_passages_returns_the_exact_refusal(self) -> None:
        agent = _FakeAgent("Some uncited general advice.")
        stored, sent, _, create_agent = await self._turn(
            [_hit("UNKNOWN PASSAGE", "zzz_9", "zzz_9_Other.txt")], agent
        )

        self.assertEqual(stored["content"], librarian_refusal())
        create_agent.assert_not_called()
        self.assertEqual(agent.inputs, [])
        chunks = "".join(frame.get("content", "") for frame in sent if frame["type"] == "chunk")
        self.assertEqual(chunks, librarian_refusal())
        end = next(frame for frame in sent if frame["type"] == "end")
        self.assertEqual(end["content"], librarian_refusal())
        self.assertNotIn("citations", end)
        self.assertNotIn("followups", end)


if __name__ == "__main__":
    unittest.main()
