"""RAG-Anything service for multimodal document processing."""

import os
import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from functools import partial
from inspect import isawaitable

logger = logging.getLogger(__name__)


def make_lightrag_doc_id(document_id: int) -> str:
    """Return the stable LightRAG document ID for an app knowledge document."""
    return f"knowledge-document-{document_id}"


class RAGAnythingService:
    """Service wrapper for RAG-Anything multimodal RAG."""

    def __init__(self):
        self.rag = None
        self.is_initialized = False
        self.output_dir = Path("./rag_anything_output")
        self.output_dir.mkdir(exist_ok=True)

    async def initialize(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        llm_model: str = "gpt-4o",
        embedding_model: str = "text-embedding-3-large",
    ):
        """Initialize RAG-Anything with LLM and embedding functions."""
        try:
            from raganything import RAGAnything, RAGAnythingConfig
            from lightrag.llm.openai import openai_complete_if_cache, openai_embed
            from lightrag.utils import EmbeddingFunc

            config = RAGAnythingConfig(
                working_dir=str(self.output_dir),
                enable_image_processing=True,
                enable_table_processing=True,
                enable_equation_processing=True,
            )

            def llm_model_func(
                prompt: str,
                system_prompt: Optional[str] = None,
                history_messages: Optional[List[Dict]] = None,
                **kwargs,
            ):
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                if history_messages:
                    messages.extend(history_messages)
                messages.append({"role": "user", "content": prompt})

                return openai_complete_if_cache(
                    model=llm_model,
                    api_key=api_key,
                    base_url=base_url,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    history_messages=history_messages or [],
                    **kwargs,
                )

            def vision_model_func(
                prompt: str,
                image_data: Optional[str] = None,
                system_prompt: Optional[str] = None,
                history_messages: Optional[List[Dict]] = None,
                **kwargs,
            ):
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                if history_messages:
                    messages.extend(history_messages)

                if image_data:
                    messages.append(
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{image_data}"
                                    },
                                },
                            ],
                        }
                    )
                else:
                    messages.append({"role": "user", "content": prompt})

                return openai_complete_if_cache(
                    model=llm_model,
                    api_key=api_key,
                    base_url=base_url,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    history_messages=history_messages or [],
                    **kwargs,
                )

            embedding_dimensions = {
                "text-embedding-3-small": 1536,
                "text-embedding-3-large": 3072,
                "text-embedding-ada-002": 1536,
            }
            embedding_dim = embedding_dimensions.get(embedding_model, 1536)

            async def embedding_func(texts: List[str], **kwargs):
                return await openai_embed.func(
                    model=embedding_model,
                    api_key=api_key,
                    base_url=base_url,
                    texts=texts,
                    embedding_dim=embedding_dim,
                    max_token_size=8192,
                    context=kwargs.get("context", "document"),
                )

            lightrag_embedding_func = EmbeddingFunc(
                embedding_dim=embedding_dim,
                max_token_size=8192,
                model_name=embedding_model,
                func=embedding_func,
                supports_asymmetric=True,
            )

            self.rag = RAGAnything(
                config=config,
                llm_model_func=llm_model_func,
                vision_model_func=vision_model_func,
                embedding_func=lightrag_embedding_func,
            )

            self.is_initialized = True
            logger.info("RAG-Anything initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize RAG-Anything: {e}")
            self.is_initialized = False

    async def shutdown(self):
        """Finalize RAG-Anything storages during application shutdown."""
        if not self.rag:
            return
        try:
            finalize = getattr(self.rag, "finalize_storages", None)
            if finalize:
                result = finalize()
                if isawaitable(result):
                    await result
        except Exception as e:
            logger.error(f"Failed to finalize RAG-Anything storages: {e}")

    async def process_document(
        self,
        file_path: str,
        parse_method: str = "auto",
        doc_id: Optional[str] = None,
        file_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process a document with RAG-Anything."""
        if not self.is_initialized or not self.rag:
            return {"success": False, "error": "RAG-Anything not initialized"}

        try:
            timeout_seconds = int(
                os.getenv("RAG_ANYTHING_PROCESS_TIMEOUT_SECONDS", "1800")
            )
            suffix = Path(file_path).suffix.lower()
            if suffix in {".md", ".markdown", ".txt"}:
                text_content = Path(file_path).read_text(
                    encoding="utf-8", errors="ignore"
                )
                init_result = await self.rag._ensure_lightrag_initialized()
                if not init_result or not init_result.get("success"):
                    raise RuntimeError(
                        "LightRAG initialization failed: "
                        f"{(init_result or {}).get('error', 'unknown error')}"
                    )
                result = await asyncio.wait_for(
                    self.rag.lightrag.ainsert(
                        input=text_content,
                        ids=doc_id,
                        file_paths=file_name or file_path,
                    ),
                    timeout=timeout_seconds,
                )
            else:
                result = await asyncio.wait_for(
                    self.rag.process_document_complete(
                        file_path=file_path,
                        output_dir=str(self.output_dir),
                        parse_method=parse_method,
                        doc_id=doc_id,
                        file_name=file_name,
                    ),
                    timeout=timeout_seconds,
                )
            logger.info(f"Processed document: {file_path}")
            return {"success": True, "result": result}
        except asyncio.TimeoutError:
            error = (
                f"RAG-Anything processing timed out after {timeout_seconds} seconds"
            )
            logger.error(error)
            return {"success": False, "error": error}
        except Exception as e:
            logger.error(f"Failed to process document: {e}")
            return {"success": False, "error": str(e)}

    async def _maybe_await(self, value):
        if isawaitable(value):
            return await value
        return value

    def _lightrag(self):
        if not self.rag:
            return None
        return getattr(self.rag, "lightrag", None) or self.rag

    def _graph_storage(self):
        lightrag = self._lightrag()
        if not lightrag:
            return None
        return getattr(lightrag, "chunk_entity_relation_graph", None)

    async def get_graph_labels(self) -> List[str]:
        """Return graph labels known to LightRAG."""
        lightrag = self._lightrag()
        if not lightrag:
            return []
        getter = getattr(lightrag, "get_graph_labels", None)
        if not getter:
            return []
        try:
            labels = await self._maybe_await(getter())
            return list(labels or [])
        except Exception as e:
            logger.error(f"Failed to get graph labels: {e}")
            return []

    async def get_knowledge_graph(
        self, node_label: str = "*", max_depth: int = 2, max_nodes: int = 500
    ) -> Dict[str, Any]:
        """Return a LightRAG knowledge graph subgraph."""
        lightrag = self._lightrag()
        if not lightrag:
            return {"nodes": [], "edges": []}
        getter = getattr(lightrag, "get_knowledge_graph", None)
        if not getter:
            return {"nodes": [], "edges": []}
        try:
            graph = await self._maybe_await(
                getter(node_label=node_label, max_depth=max_depth, max_nodes=max_nodes)
            )
            return self._normalize_knowledge_graph(graph)
        except TypeError:
            try:
                graph = await self._maybe_await(
                    getter(node_label, max_depth=max_depth, max_nodes=max_nodes)
                )
                return self._normalize_knowledge_graph(graph)
            except Exception as e:
                logger.error(f"Failed to get knowledge graph: {e}")
                return {"nodes": [], "edges": []}
        except Exception as e:
            logger.error(f"Failed to get knowledge graph: {e}")
            return {"nodes": [], "edges": []}

    def _object_to_dict(self, value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        if hasattr(value, "model_dump"):
            return value.model_dump()
        if hasattr(value, "__dict__"):
            return {
                key: item
                for key, item in vars(value).items()
                if not key.startswith("_")
            }
        return {"value": value}

    def _normalize_node(self, raw: Any, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if data is not None:
            node = dict(data)
            node.setdefault("id", str(raw))
            return node
        node = self._object_to_dict(raw)
        node_id = node.get("id") or node.get("entity_id") or node.get("name")
        if node_id is None and "value" in node:
            node_id = node["value"]
        node["id"] = str(node_id or "")
        return node

    def _normalize_edge(
        self,
        raw: Any,
        target: Optional[Any] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if target is not None:
            edge = dict(data or {})
            edge.setdefault("source", str(raw))
            edge.setdefault("target", str(target))
            return edge
        if isinstance(raw, (list, tuple)):
            if len(raw) >= 3:
                return self._normalize_edge(raw[0], raw[1], raw[2] or {})
            if len(raw) == 2:
                return self._normalize_edge(raw[0], raw[1], {})
        edge = self._object_to_dict(raw)
        source = edge.get("source") or edge.get("src_id") or edge.get("source_id")
        target_id = edge.get("target") or edge.get("tgt_id") or edge.get("target_id")
        if source is not None:
            edge["source"] = str(source)
        if target_id is not None:
            edge["target"] = str(target_id)
        return edge

    def _normalize_knowledge_graph(self, graph: Any) -> Dict[str, Any]:
        if isinstance(graph, dict):
            nodes = graph.get("nodes", [])
            edges = graph.get("edges", [])
        else:
            nodes = getattr(graph, "nodes", [])
            edges = getattr(graph, "edges", [])
        return {
            "nodes": [self._normalize_node(node) for node in nodes or []],
            "edges": [self._normalize_edge(edge) for edge in edges or []],
        }

    async def get_all_graph_nodes(self) -> List[Dict[str, Any]]:
        """Return all graph nodes when supported by the active graph storage."""
        storage = self._graph_storage()
        if not storage:
            return []
        try:
            getter = getattr(storage, "get_all_nodes", None)
            if getter:
                raw_nodes = await self._maybe_await(getter())
                nodes = []
                for raw_node in raw_nodes or []:
                    if isinstance(raw_node, str):
                        node_getter = getattr(storage, "get_node", None)
                        data = (
                            await self._maybe_await(node_getter(raw_node))
                            if node_getter
                            else {}
                        )
                        nodes.append(self._normalize_node(raw_node, data or {}))
                    else:
                        nodes.append(self._normalize_node(raw_node))
                return nodes

            graph = getattr(storage, "_graph", None) or getattr(storage, "graph", None)
            if graph is not None and hasattr(graph, "nodes"):
                return [
                    self._normalize_node(node_id, data)
                    for node_id, data in graph.nodes(data=True)
                ]
        except Exception as e:
            logger.error(f"Failed to get all graph nodes: {e}")
        return []

    async def get_all_graph_edges(self) -> List[Dict[str, Any]]:
        """Return all graph edges when supported by the active graph storage."""
        storage = self._graph_storage()
        if not storage:
            return []
        try:
            getter = getattr(storage, "get_all_edges", None)
            if getter:
                raw_edges = await self._maybe_await(getter())
                return [self._normalize_edge(edge) for edge in raw_edges or []]

            graph = getattr(storage, "_graph", None) or getattr(storage, "graph", None)
            if graph is not None and hasattr(graph, "edges"):
                return [
                    self._normalize_edge(source, target, data)
                    for source, target, data in graph.edges(data=True)
                ]
        except Exception as e:
            logger.error(f"Failed to get all graph edges: {e}")
        return []

    async def export_graph_markdown(self, output_path: str) -> None:
        """Export graph data to markdown for diagnostics."""
        lightrag = self._lightrag()
        if not lightrag:
            return
        exporter = getattr(lightrag, "aexport_data", None)
        if not exporter:
            return
        await self._maybe_await(exporter(output_path, file_format="md"))

    async def delete_document_from_graph(self, doc_id: str) -> Dict[str, Any]:
        """Delete a source document from the LightRAG graph."""
        lightrag = self._lightrag()
        if not lightrag:
            return {"success": False, "error": "RAG-Anything not initialized"}
        deleter = getattr(lightrag, "adelete_by_doc_id", None)
        if not deleter:
            return {"success": False, "error": "LightRAG document deletion unavailable"}
        try:
            try:
                result = await self._maybe_await(deleter(doc_id, delete_llm_cache=True))
            except TypeError:
                result = await self._maybe_await(deleter(doc_id))
            status = getattr(result, "status", None)
            message = getattr(result, "message", None)
            if isinstance(result, dict):
                status = result.get("status", status)
                message = result.get("message", message)
            return {
                "success": status in (None, "success", "ok", True),
                "status": status,
                "message": message,
            }
        except Exception as e:
            logger.error(f"Failed to delete LightRAG document {doc_id}: {e}")
            return {"success": False, "error": str(e)}

    async def process_folder(
        self,
        folder_path: str,
        parse_method: str = "auto",
    ) -> Dict[str, Any]:
        """Process all documents in a folder."""
        if not self.is_initialized or not self.rag:
            return {"success": False, "error": "RAG-Anything not initialized"}

        try:
            result = await self.rag.process_folder_complete(
                folder_path=folder_path,
                output_dir=str(self.output_dir),
                parse_method=parse_method,
            )
            logger.info(f"Processed folder: {folder_path}")
            return {"success": True, "result": result}
        except Exception as e:
            logger.error(f"Failed to process folder: {e}")
            return {"success": False, "error": str(e)}

    async def query(
        self,
        query_text: str,
        mode: str = "hybrid",
    ) -> Dict[str, Any]:
        """Query the processed knowledge base."""
        if not self.is_initialized or not self.rag:
            return {"success": False, "error": "RAG-Anything not initialized"}

        try:
            result = await self.rag.aquery(query_text, mode=mode)
            return {"success": True, "result": result}
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return {"success": False, "error": str(e)}

    async def query_multimodal(
        self,
        query_text: str,
        multimodal_content: List[Dict[str, Any]],
        mode: str = "hybrid",
    ) -> Dict[str, Any]:
        """Query with multimodal content (images, equations, tables)."""
        if not self.is_initialized or not self.rag:
            return {"success": False, "error": "RAG-Anything not initialized"}

        try:
            result = await self.rag.aquery_with_multimodal(
                query_text,
                multimodal_content=multimodal_content,
                mode=mode,
            )
            return {"success": True, "result": result}
        except Exception as e:
            logger.error(f"Multimodal query failed: {e}")
            return {"success": False, "error": str(e)}

    async def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Search the knowledge base for relevant documents."""
        result = await self.query(query, mode="hybrid")
        if result.get("success"):
            return [{"content": result.get("result", ""), "score": 1.0}]
        return []


rag_anything_service = RAGAnythingService()
