"""LLM provider implementations for different services."""

from typing import Optional, Any, Iterator
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
import httpx
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_community.embeddings import FastEmbedEmbeddings


class SarvamLLM(BaseChatModel):
    """Custom LLM implementation for Sarvam AI with streaming support."""

    api_key: str
    model: str = "sarvam-m"
    base_url: str = "https://api.sarvam.ai"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Generate response from Sarvam API."""
        # Convert messages to Sarvam format
        sarvam_messages = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                sarvam_messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                sarvam_messages.append({"role": "assistant", "content": msg.content})
            elif isinstance(msg, SystemMessage):
                sarvam_messages.append({"role": "system", "content": msg.content})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "messages": sarvam_messages,
            "model": self.model,
        }

        response = httpx.post(
            f"{self.base_url}/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60.0,
        )

        if response.status_code != 200:
            raise Exception(
                f"Sarvam API error: {response.status_code} - {response.text}"
            )

        data = response.json()
        content = data["choices"][0]["message"]["content"]

        generation = ChatGeneration(message=AIMessage(content=content))
        return ChatResult(generations=[generation])

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
