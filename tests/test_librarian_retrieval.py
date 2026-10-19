"""Librarian retrieval is scoped to Library and Reference Documents."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from backend.config import config
from backend.services import library
from backend.services.graphrag_service import GraphRAGService


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


def _hit(text: str, file_id: str | None, filename: str, score: float = 0.9) -> dict:
    payload = {"text": text, "filename": filename, "chunk_index": 0, "title": "drive name"}
    if file_id:
        payload["google_file_id"] = file_id
    return {"score": score, "payload": payload}


class LibrarianRetrievalTests(unittest.IsolatedAsyncioTestCase):
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
        self.service = GraphRAGService()
        self.service._neo4j_ready = True
        self.service.find_subgraph = AsyncMock(return_value="Entity: Unattributed fact")
        self.service.qdrant_ready = AsyncMock(return_value=True)
        self.service._embed_query = AsyncMock(return_value=[0.1, 0.2])

    async def retrieve(self, hits: list[dict]):
        self.service._search_qdrant = AsyncMock(return_value=hits)
        return await self.service.retrieve_library_context("how is trust built?")

    async def test_only_library_and_reference_passages_reach_the_model(self) -> None:
        text, citations = await self.retrieve([
            _hit("LIBRARY PASSAGE", "lib_1", "lib_1_Practice One.txt"),
            _hit("REFERENCE PASSAGE", "ref_1", "ref_1_Charter.txt"),
            _hit("UNKNOWN PASSAGE", "other_9", "other_9_Elsewhere.txt"),
            _hit("NO PROVENANCE PASSAGE", None, "loose.txt"),
            _hit("ROOT FOLDER COPY", "lib_1", "lib_1_drive name.txt"),
        ])

        self.assertIn("LIBRARY PASSAGE", text)
        self.assertIn("REFERENCE PASSAGE", text)
        self.assertNotIn("UNKNOWN PASSAGE", text)
        self.assertNotIn("NO PROVENANCE PASSAGE", text)
        self.assertNotIn("ROOT FOLDER COPY", text)
        self.assertIn("[Source: Practice One", text)
        self.assertIn("/api/library/documents/lib_1/file", text)
        self.assertEqual([c["id"] for c in citations], ["lib_1", "ref_1"])

    async def test_unattributed_graph_facts_are_dropped(self) -> None:
        text, _ = await self.retrieve([_hit("LIBRARY PASSAGE", "lib_1", "lib_1_Practice One.txt")])

        self.assertNotIn("Unattributed fact", text)

    async def test_no_corpus_passages_yields_no_context(self) -> None:
        text, citations = await self.retrieve([_hit("UNKNOWN PASSAGE", "other_9", "x.txt")])

        self.assertEqual(text, "")
        self.assertEqual(citations, [])

    async def test_citation_payload(self) -> None:
        _, citations = await self.retrieve([
            _hit("A", "lib_1", "lib_1_Practice One.txt"),
            _hit("B", "lib_1", "lib_1_Practice One.txt", score=0.5),
            _hit("C", "ref_1", "ref_1_Charter.txt"),
        ])

        self.assertEqual(
            citations,
            [
                {
                    "id": "lib_1",
                    "title": "Practice One",
                    "type": "LSP",
                    "systems": ["trust", "engage"],
                    "url": "/api/library/documents/lib_1/file",
                },
                {
                    "id": "ref_1",
                    "title": "Charter",
                    "type": "Reference",
                    "systems": [],
                    "url": "/api/library/documents/ref_1/file",
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
