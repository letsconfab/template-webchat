"""Configuration management for the copilot chat application."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Application configuration loaded from environment variables."""
    
    # Application Configuration
    PURPOSE: str = os.getenv("PURPOSE", "You are a helpful AI assistant.")
    GAURDRAILS: str = os.getenv("GAURDRAILS", "Be polite and professional.")
    
    # Feature Flags
    STORE_CHAT_THREADS: bool = os.getenv("STORE_CHAT_THREADS", "true").lower() == "true"
    USE_EMAIL_AS_IDENTIFIER: bool = os.getenv("USE_EMAIL_AS_IDENTIFIER", "true").lower() == "true"
    
    # Knowledge Base Configuration
    KB_ASSETS_DIR: Path = Path(os.getenv("KB_ASSETS_DIR", "./kb_assets"))
    
    # Langfuse Observability
    LANGFUSE_BASE_URL: str | None = os.getenv("LANGFUSE_BASE_URL") or None
    LANGFUSE_PUBLIC_KEY: str | None = os.getenv("LANGFUSE_PUBLIC_KEY") or None
    LANGFUSE_SECRET_KEY: str | None = os.getenv("LANGFUSE_SECRET_KEY") or None
    
    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    
    # Database Configuration
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost/webchat_db")
    
    # JWT Configuration
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-super-secret-jwt-key-change-this-in-production")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    
    # Email Configuration
    SMTP_SERVER: str = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    FROM_EMAIL: str = os.getenv("FROM_EMAIL", "")
    
    @property
    def langfuse_enabled(self) -> bool:
        """Check if Langfuse observability is configured."""
        return all([
            self.LANGFUSE_BASE_URL,
            self.LANGFUSE_PUBLIC_KEY,
            self.LANGFUSE_SECRET_KEY
        ])
    
    @property
    def system_prompt(self) -> str:
        """Generate the complete system prompt with purpose and guardrails."""
        return f"""{self.PURPOSE}

Guardrails:
{self.GAURDRAILS}

Use the provided knowledge base to answer questions accurately. If the answer is not in the knowledge base, say so clearly."""


# Global config instance
config = Config()
