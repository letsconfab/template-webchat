"""RAG-Anything service for multimodal document processing."""

import os
import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from functools import partial

logger = logging.getLogger(__name__)


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

            def embedding_func(input: List[str]) -> List[List[float]]:
                return openai_embed(
                    model=embedding_model,
                    api_key=api_key,
                    base_url=base_url,
                    input=input,
                )

            self.rag = RAGAnything(
                config=config,
                llm_model_func=llm_model_func,
                vision_model_func=vision_model_func,
                embedding_func=embedding_func,
            )

            await self.rag.finalize_storages()
            self.is_initialized = True
            logger.info("RAG-Anything initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize RAG-Anything: {e}")
            self.is_initialized = False

    async def process_document(
        self,
        file_path: str,
        parse_method: str = "auto",
    ) -> Dict[str, Any]:
        """Process a document with RAG-Anything."""
        if not self.is_initialized or not self.rag:
            return {"success": False, "error": "RAG-Anything not initialized"}

        try:
            result = await self.rag.process_document_complete(
                file_path=file_path,
                output_dir=str(self.output_dir),
                parse_method=parse_method,
            )
            logger.info(f"Processed document: {file_path}")
            return {"success": True, "result": result}
        except Exception as e:
            logger.error(f"Failed to process document: {e}")
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
