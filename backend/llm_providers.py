"""LLM provider implementations for different services."""

import json
from typing import Any, Callable, Optional, Sequence, Literal
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
import httpx
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from langchain_community.embeddings import FastEmbedEmbeddings


class SarvamLLM(BaseChatModel):
    """Custom LLM implementation for Sarvam AI with streaming support."""

    api_key: str
    model: str = "sarvam-30b"
    base_url: str = "https://api.sarvam.ai"

    @staticmethod
    def _extract_content(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append(block.get("text", ""))
                    elif block.get("type") == "text_delta":
                        parts.append(block.get("text", ""))
            return "\n".join(parts)
        return str(content)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Generate response from Sarvam API."""
        sarvam_messages = []
        for msg in messages:
            role = "user"
            if isinstance(msg, SystemMessage):
                role = "system"
            elif isinstance(msg, AIMessage):
                role = "assistant"
            sarvam_messages.append({"role": role, "content": self._extract_content(msg.content)})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "messages": sarvam_messages,
            "model": self.model,
        }

        if "tools" in kwargs and kwargs["tools"]:
            payload["tools"] = kwargs["tools"]
        if "tool_choice" in kwargs:
            payload["tool_choice"] = kwargs["tool_choice"]

        response = httpx.post(
            f"{self.base_url}/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=300.0,
        )

        if response.status_code != 200:
            raise Exception(
                f"Sarvam API error: {response.status_code} - {response.text}"
            )

        data = response.json()
        choice = data["choices"][0]
        message = choice["message"]

        content = message.get("content")
        raw_tool_calls = message.get("tool_calls")

        if raw_tool_calls:
            tool_calls = []
            for tc in raw_tool_calls:
                tool_calls.append({
                    "name": tc["function"]["name"],
                    "args": json.loads(tc["function"]["arguments"]),
                    "id": tc["id"],
                })
            generation = ChatGeneration(
                message=AIMessage(
                    content=content or "",
                    tool_calls=tool_calls,
                    additional_kwargs={"tool_calls": raw_tool_calls},
                )
            )
        else:
            generation = ChatGeneration(message=AIMessage(content=content or ""))

        return ChatResult(generations=[generation])

    def bind_tools(
        self,
        tools: Sequence[BaseTool | dict[str, Any] | type | Callable],
        *,
        tool_choice: dict | str | Literal["any", "auto", "none"] | bool | None = None,
        **kwargs: Any,
    ) -> Runnable[Any, Any]:
        from langchain_core.utils.function_calling import convert_to_openai_tool
        formatted = [convert_to_openai_tool(t) for t in tools]
        return self.bind(tools=formatted, tool_choice=tool_choice, **kwargs)

    @property
    def _llm_type(self) -> str:
        return "sarvam"


class LLMProvider:
    """Base class for LLM providers."""

    def __init__(self, provider: str, model: str, api_key: Optional[str] = None):
        self.provider = provider
        self.model = model
        self.api_key = api_key

    def get_llm(self, callbacks=None):
        """Get the LLM instance for this provider."""
        if self.provider == "openai":
            return ChatOpenAI(
                model=self.model,
                api_key=self.api_key,
                streaming=True,
                callbacks=callbacks,
            )
        elif self.provider == "groq":
            return ChatGroq(
                model=self.model,
                api_key=self.api_key,
                streaming=True,
                callbacks=callbacks,
            )
        elif self.provider == "ollama":
            return ChatOllama(
                model=self.model,
                streaming=True,
                callbacks=callbacks,
            )
        elif self.provider == "sarvam":
            return SarvamLLM(
                api_key=self.api_key,
                model=self.model,
            )
        else:
            return ChatOpenAI(
                model="gpt-4o-mini",
                api_key=self.api_key,
                streaming=True,
                callbacks=callbacks,
            )

    def get_embeddings(self):
        """Get embeddings for this provider."""
        # Use local FastEmbed for all providers to avoid API key conflicts
        import os
        import tempfile

        cache_dir = os.path.join(tempfile.gettempdir(), "langchain_cache")
        os.makedirs(cache_dir, exist_ok=True)
        os.environ["HF_HOME"] = cache_dir
        os.environ["TRANSFORMERS_CACHE"] = cache_dir
        return FastEmbedEmbeddings(cache_dir=cache_dir)


async def get_available_models(provider: str, api_key: str) -> list[str]:
    """Fetch available models dynamically from the provider's API."""
    if provider == "openai":
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0,
            )
            if response.status_code == 200:
                data = response.json()
                # Filter for chat models
                models = [
                    model["id"]
                    for model in data.get("data", [])
                    if model.get("id", "").startswith(("gpt-", "o1-"))
                ]
                return sorted(models)
            raise Exception(f"Failed to fetch OpenAI models: {response.status_code}")

    elif provider == "groq":
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0,
            )
            if response.status_code == 200:
                data = response.json()
                models = [model["id"] for model in data.get("data", [])]
                return sorted(models)
            raise Exception(f"Failed to fetch Groq models: {response.status_code}")

    elif provider == "ollama":
        # Ollama runs locally, no API key needed
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:11434/api/tags", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                models = [model["name"] for model in data.get("models", [])]
                return sorted(models)
            raise Exception("Ollama is not running. Please start Ollama first.")

    elif provider == "sarvam":
        # Sarvam doesn't have a public models API
        return ["sarvam-105b", "sarvam-30b", "sarvam-m"]

    else:
        raise Exception(f"Unknown provider: {provider}")


async def validate_api_key(provider: str, api_key: str) -> bool:
    """Validate API key for a provider."""
    # Simple validation - in production, you'd make an actual API call
    if provider == "ollama":
        return True  # Ollama doesn't need API key
    if not api_key or len(api_key) < 10:
        return False
    return True
