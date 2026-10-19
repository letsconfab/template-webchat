"""Configuration management for the admin invite application."""

import logging
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)

# Known insecure defaults — validate_config() refuses to run production with these
_DEFAULT_SECRET_KEY = "your-super-secret-jwt-key-change-this-in-production"
_DEFAULT_NEO4J_PASSWORD = "cocoindex"


class Config:
    """Application configuration loaded from environment variables."""

    # Environment: development (default) or production
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development").lower()

    # Feature Flags
    USE_EMAIL_AS_IDENTIFIER: bool = (
        os.getenv("USE_EMAIL_AS_IDENTIFIER", "true").lower() == "true"
    )

    # Database Configuration
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/webchat_db",
    )

    # JWT Configuration
    SECRET_KEY: str = os.getenv(
        "SECRET_KEY", "your-super-secret-jwt-key-change-this-in-production"
    )
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
    )

    # Email Configuration
    SMTP_SERVER: str = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    FROM_EMAIL: str = os.getenv("FROM_EMAIL", "")

    # Frontend URL Configuration (comma-separated list allowed; first entry is primary)
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")

    @property
    def IS_PRODUCTION(self) -> bool:
        return self.ENVIRONMENT in ("production", "prod")

    @property
    def FRONTEND_ORIGINS(self) -> list[str]:
        return [
            origin.strip().rstrip("/")
            for origin in self.FRONTEND_URL.split(",")
            if origin.strip()
        ]

    @property
    def PRIMARY_FRONTEND_ORIGIN(self) -> str:
        origins = self.FRONTEND_ORIGINS
        return origins[0] if origins else "http://localhost:5173"

    @property
    def CORS_ORIGINS(self) -> list[str]:
        origins = list(self.FRONTEND_ORIGINS)
        if not self.IS_PRODUCTION:
            for dev_origin in (
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:3000",
                "http://localhost:8000",
            ):
                if dev_origin not in origins:
                    origins.append(dev_origin)
        return origins

    # Knowledge Base Configuration
    KB_CACHE_DIR: str = os.getenv("KB_CACHE_DIR", "./kb_cache")
    # Served Library Document PDFs and library.json. Must not sit under
    # KB_CACHE_DIR: the indexer walks that tree and would index served copies.
    LIBRARY_FILES_DIR: str = os.getenv("LIBRARY_FILES_DIR", "./library_files")

    # Librarian persona. Deployment-specific names come from the environment
    # (this repository is public); the defaults are neutral placeholders.
    LIBRARIAN_LIBRARY_NAME: str = os.getenv("LIBRARIAN_LIBRARY_NAME", "Resource")
    LIBRARIAN_ORGANIZATION_NAME: str = os.getenv(
        "LIBRARIAN_ORGANIZATION_NAME", "the organization"
    )

    # Google Drive OAuth
    GOOGLE_OAUTH_CLIENT_ID: str = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
    GOOGLE_OAUTH_CLIENT_SECRET: str = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
    GOOGLE_OAUTH_REDIRECT_URI: str = os.getenv(
        "GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8000/api/drive/callback"
    )

    # Neo4j
    NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "cocoindex")

    # Qdrant
    QDRANT_URL: str = os.getenv("QDRANT_URL", "http://localhost:6333")


# Global config instance
config = Config()


def validate_config(cfg: Config) -> None:
    """Check for insecure defaults. Hard-fail in production, warn in development.

    Called from the app lifespan rather than at import time so that alembic,
    scripts, and tests can import config without side effects.
    """
    validate_library_dirs(cfg)

    problems: list[str] = []

    if cfg.SECRET_KEY == _DEFAULT_SECRET_KEY:
        problems.append("SECRET_KEY is the insecure default — set a real value in .env")
    elif len(cfg.SECRET_KEY) < 32:
        problems.append("SECRET_KEY is too short (need >= 32 chars)")

    if cfg.NEO4J_PASSWORD == _DEFAULT_NEO4J_PASSWORD:
        problems.append("NEO4J_PASSWORD is the insecure default — set a real value in .env")

    if cfg.IS_PRODUCTION and cfg.FRONTEND_URL.startswith("http://localhost"):
        problems.append("FRONTEND_URL is not set for production (still localhost)")

    if not problems:
        return

    if cfg.IS_PRODUCTION:
        raise RuntimeError(
            "Refusing to start in production with insecure configuration:\n - "
            + "\n - ".join(problems)
        )

    for problem in problems:
        logger.warning("Insecure config (ok in development): %s", problem)


def validate_library_dirs(cfg: Config) -> None:
    """Refuse to start when LIBRARY_FILES_DIR sits inside KB_CACHE_DIR.

    The indexer walks KB_CACHE_DIR recursively and indexes PDFs, so served
    Library Document copies there would be indexed twice. Applies in every
    environment.
    """
    kb_cache = Path(cfg.KB_CACHE_DIR).resolve()
    library_files = Path(cfg.LIBRARY_FILES_DIR).resolve()
    if library_files == kb_cache or library_files.is_relative_to(kb_cache):
        raise RuntimeError(
            f"LIBRARY_FILES_DIR ({cfg.LIBRARY_FILES_DIR}) must not be inside "
            f"KB_CACHE_DIR ({cfg.KB_CACHE_DIR}); the indexer would index served copies."
        )
