"""Langfuse service for tracing and observability."""

from typing import Optional, Any
from contextlib import contextmanager
from langfuse import Langfuse, get_client, propagate_attributes


class LangfuseService:
    """Service for Langfuse tracing."""

    def __init__(self):
        self._initialized = False
        self._public_key: Optional[str] = None
        self._secret_key: Optional[str] = None
        self._base_url: Optional[str] = None

    def initialize(
        self,
        public_key: str,
        secret_key: str,
        base_url: str = "https://us.cloud.langfuse.com",
    ):
        """Initialize Langfuse client."""
        if not public_key or not secret_key:
            self._initialized = False
            return

        try:
            self._public_key = public_key
            self._secret_key = secret_key
            self._base_url = base_url

            # Initialize Langfuse client using the standard pattern
            Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=base_url,
            )
            self._initialized = True
            print(f"Langfuse initialized with base_url: {base_url}")
        except Exception as e:
            print(f"Error initializing Langfuse: {e}")
            self._initialized = False

    def is_initialized(self) -> bool:
        """Check if Langfuse is initialized."""
        return self._initialized

    def get_client(self) -> Optional[Langfuse]:
        """Get the Langfuse client."""
        if not self.is_initialized():
            return None
        try:
            return get_client(public_key=self._public_key)
        except Exception as e:
            print(f"Error getting Langfuse client: {e}")
            return None

    @contextmanager
    def trace_chat(self, session_id: str, user_id: Optional[str] = None):
        """Create a trace context for a chat session with session_id and user_id."""
        if not self.is_initialized():
            yield None
            return

        client = self.get_client()
        if not client:
            yield None
            return

        try:
            with propagate_attributes(session_id=session_id, user_id=user_id):
                with client.start_as_current_observation(
                    as_type="span",
                    name=f"chat-{session_id}",
                ) as span:
                    yield span
        except Exception as e:
            print(f"Error in trace context: {e}")
            yield None

    @contextmanager
    def trace_generation(self, parent_span, model: str):
        """Create a nested generation span for LLM response."""
        if not parent_span:
            yield None
            return

        try:
            with parent_span.start_as_current_observation(
                as_type="generation",
                name="llm-response",
                model=model,
            ) as generation:
                yield generation
        except Exception as e:
            print(f"Error creating generation trace: {e}")
            yield None

    def flush(self):
        """Flush any pending traces."""
        try:
            client = self.get_client()
            if client:
                client.flush()
        except Exception as e:
            print(f"Error flushing Langfuse: {e}")

    def get_trace_url(self, session_id: str) -> Optional[str]:
        """Get the trace URL for a session."""
        if not self._base_url:
            return None
        return f"{self._base_url}/project/settings/public"


langfuse_service = LangfuseService()
