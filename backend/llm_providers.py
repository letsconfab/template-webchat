"""LLM provider implementations for different services."""
from typing import Optional
import httpx
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage


class LLMProvider:
    """Base class for LLM providers."""
    
    def __init__(self, provider: str, model: str, api_key: Optional[str] = None):
        self.provider = provider
        self.model = model
        self.api_key = api_key
    
    def get_llm(self):
        """Get the LLM instance for this provider."""
        if self.provider == "openai":
            return ChatOpenAI(
                model=self.model,
                api_key=self.api_key,
                streaming=True,
            )
        elif self.provider == "groq":
            return ChatGroq(
                model=self.model,
                api_key=self.api_key,
                streaming=True,
            )
        elif self.provider == "ollama":
            return ChatOllama(
                model=self.model,
                streaming=True,
            )
        elif self.provider == "sarvam":
            # Sarvam doesn't have LangChain integration, will use custom implementation
            return None
        else:
            return ChatOpenAI(
                model="gpt-4o-mini",
                api_key=self.api_key,
                streaming=True,
            )
    
    def get_embeddings(self):
        """Get embeddings for this provider."""
        if self.provider == "openai":
            return OpenAIEmbeddings(api_key=self.api_key)
        elif self.provider == "groq":
            # Groq doesn't have embeddings API, fallback to OpenAI
            return OpenAIEmbeddings(api_key=self.api_key)
        elif self.provider == "ollama":
            return OllamaEmbeddings()
        elif self.provider == "sarvam":
            # Sarvam doesn't have embeddings API in LangChain, fallback to OpenAI
            return OpenAIEmbeddings(api_key=self.api_key)
        else:
            return OpenAIEmbeddings(api_key=self.api_key)


async def get_available_models(provider: str, api_key: str) -> list[str]:
    """Fetch available models dynamically from the provider's API."""
    if provider == "openai":
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0
            )
            if response.status_code == 200:
                data = response.json()
                # Filter for chat models
                models = [
                    model["id"] for model in data.get("data", [])
                    if model.get("id", "").startswith(("gpt-", "o1-"))
                ]
                return sorted(models)
            raise Exception(f"Failed to fetch OpenAI models: {response.status_code}")
    
    elif provider == "groq":
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0
            )
            if response.status_code == 200:
                data = response.json()
                models = [model["id"] for model in data.get("data", [])]
                return sorted(models)
            raise Exception(f"Failed to fetch Groq models: {response.status_code}")
    
    elif provider == "ollama":
        # Ollama runs locally, no API key needed
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "http://localhost:11434/api/tags",
                timeout=5.0
            )
            if response.status_code == 200:
                data = response.json()
                models = [model["name"] for model in data.get("models", [])]
                return sorted(models)
            raise Exception("Ollama is not running. Please start Ollama first.")
    
    elif provider == "sarvam":
        # Sarvam doesn't have a public models API
        return ["sarvam-1", "sarvam-2b"]
    
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
