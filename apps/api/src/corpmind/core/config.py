"""Application settings — all configuration from environment variables.

Uses pydantic-settings so every field is type-validated at startup.
Never access os.environ directly; always go through `settings`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env relative to this file (apps/api/src/corpmind/core/config.py)
# so the path is correct regardless of where uvicorn is started from.
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── Application ───────────────────────────────────────────────────────────
    APP_ENV: Literal["development", "staging", "production"] = "development"
    APP_DEBUG: bool = False
    APP_SECRET_KEY: str
    # Both ports included: Next.js defaults to 3000 but falls back to 3001
    # when 3000 is occupied (common on a dev machine with multiple projects).
    APP_ALLOWED_HOSTS: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
    ]

    # ── JWT ───────────────────────────────────────────────────────────────────
    JWT_ALGORITHM: str = "RS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    JWT_PRIVATE_KEY: str = ""
    JWT_PUBLIC_KEY: str = ""

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_TIMEOUT: int = 30

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_POOL_SIZE: int = 20

    # ── Celery ────────────────────────────────────────────────────────────────
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # ── Qdrant ────────────────────────────────────────────────────────────────
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""

    # ── Meilisearch ───────────────────────────────────────────────────────────
    MEILISEARCH_URL: str = "http://localhost:7700"
    MEILISEARCH_MASTER_KEY: str = ""

    # ── Euri AI Gateway ───────────────────────────────────────────────────────
    EURI_API_KEY: str
    EURI_API_BASE_URL: str = "https://api.euron.one/api/v1/euri/"
    EURI_TIMEOUT_SECONDS: int = 60
    EURI_MAX_RETRIES: int = 3

    # ── Email / SMTP ──────────────────────────────────────────────────────────
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_ADDRESS: str = "noreply@corpmind.local"
    SMTP_USE_TLS: bool = False

    # ── Channel tokens ────────────────────────────────────────────────────────
    WHATSAPP_BUSINESS_ACCOUNT_ID: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_WEBHOOK_VERIFY_TOKEN: str = ""
    WHATSAPP_WEBHOOK_SECRET: str = ""

    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WEBHOOK_SECRET: str = ""

    META_APP_ID: str = ""
    META_APP_SECRET: str = ""
    META_WEBHOOK_SECRET: str = ""

    LINKEDIN_CLIENT_ID: str = ""
    LINKEDIN_CLIENT_SECRET: str = ""

    # ── Cloudinary ────────────────────────────────────────────────────────────
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    # ── Observability ─────────────────────────────────────────────────────────
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"
    SENTRY_DSN: str = ""
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"
    LOG_LEVEL: str = "INFO"

    # ── AI Cost Governance ────────────────────────────────────────────────────
    AI_DEFAULT_BUDGET_INR: float = 400.0
    AI_SEMANTIC_CACHE_THRESHOLD: float = 0.96

    # ── Email Message-ID ──────────────────────────────────────────────────────
    # Domain used as the right-hand side of SMTP Message-ID headers.
    # Format: <ULID@MAIL_DOMAIN>  — e.g. <01ARZ3NDEKTSV4RRFFQ69G5FAV@corpmind.ai>
    # Auto-derived from SMTP_FROM_ADDRESS if left empty.
    # Required in production (startup fails if both MAIL_DOMAIN and SMTP_FROM_ADDRESS lack a domain).
    MAIL_DOMAIN: str = ""

    # ── Inbox / Field Encryption ──────────────────────────────────────────────
    # INBOX_ENCRYPTION_KEY_V1: 64 hex characters = 32 bytes (AES-256 key).
    # Generate: python -c "import os; print(os.urandom(32).hex())"
    # Required in production. Optional in dev (inbox encrypt/decrypt raises if unset).
    INBOX_ENCRYPTION_KEY_V1: str = ""
    # Active key version used for all new encryptions. Old rows decrypt via the
    # version byte embedded in their ciphertext blob — no schema change on rotation.
    INBOX_ENCRYPTION_KEY_VERSION: int = 1

    # ── Google OAuth (Gmail inbox integration) ────────────────────────────────
    # Register at https://console.cloud.google.com/ → APIs & Services → Credentials
    # Required scopes: openid email https://www.googleapis.com/auth/gmail.readonly
    # Optional in dev. Inbox /connect and /callback raise 422 if unset when called.
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    # Must match exactly what is registered in Google Cloud Console.
    # Development: http://localhost:8000/api/v1/inbox/callback
    GOOGLE_REDIRECT_URI: str = ""

    @field_validator("APP_SECRET_KEY")
    @classmethod
    def secret_key_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("APP_SECRET_KEY must be at least 32 characters")
        return v

    @field_validator("INBOX_ENCRYPTION_KEY_V1")
    @classmethod
    def validate_inbox_key_v1(cls, v: str) -> str:
        if not v:
            return v
        try:
            key_bytes = bytes.fromhex(v)
        except ValueError as exc:
            raise ValueError("INBOX_ENCRYPTION_KEY_V1 must be valid hexadecimal") from exc
        if len(key_bytes) != 32:
            raise ValueError(
                f"INBOX_ENCRYPTION_KEY_V1 must be exactly 64 hex characters (32 bytes); "
                f"got {len(key_bytes)} bytes"
            )
        return v

    @model_validator(mode="after")
    def ensure_mail_domain(self) -> "Settings":
        """Derive MAIL_DOMAIN from SMTP_FROM_ADDRESS when not explicitly set."""
        if not self.MAIL_DOMAIN:
            smtp_from = self.SMTP_FROM_ADDRESS
            if "@" in smtp_from:
                self.MAIL_DOMAIN = smtp_from.split("@")[-1]
        if self.APP_ENV == "production" and not self.MAIL_DOMAIN:
            raise ValueError(
                "MAIL_DOMAIN must be set in production (or set SMTP_FROM_ADDRESS to "
                "an address with a domain so it can be auto-derived)."
            )
        return self

    @model_validator(mode="after")
    def ensure_inbox_encryption_key_in_production(self) -> "Settings":
        if self.APP_ENV == "production" and not self.INBOX_ENCRYPTION_KEY_V1:
            raise ValueError(
                "INBOX_ENCRYPTION_KEY_V1 must be set in production. "
                'Generate with: python -c "import os; print(os.urandom(32).hex())"'
            )
        return self

    @model_validator(mode="after")
    def ensure_jwt_keys(self) -> "Settings":
        """Generate ephemeral RS256 keys in dev if not provided in .env."""
        if self.JWT_PRIVATE_KEY:
            return self
        if self.APP_ENV == "production":
            raise ValueError("JWT_PRIVATE_KEY must be set in production")
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.JWT_PRIVATE_KEY = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
        self.JWT_PUBLIC_KEY = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
        return self

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def database_url_sync(self) -> str:
        """Synchronous database URL for Alembic migrations."""
        return self.DATABASE_URL.replace("+asyncpg", "")


settings = Settings()  # type: ignore[call-arg]
