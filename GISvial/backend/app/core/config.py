"""GIS — config."""
import os


class Settings:
    app_name: str = "SALVI GIS API"
    app_version: str = "0.3.1"

    # Database
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://luxstudio:luxstudio@localhost:5432/luxstudio",
    )
    db_pool_size: int = int(os.getenv("DB_POOL_SIZE", "10"))
    db_max_overflow: int = int(os.getenv("DB_MAX_OVERFLOW", "20"))

    # Auth
    oidc_issuer_url: str = os.getenv("OIDC_ISSUER_URL", "")

    # Anthropic
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    salvi_ai_model: str = os.getenv("SALVI_AI_MODEL", "claude-haiku-4-5-20251001")

    # Cors
    cors_origins: str = os.getenv("CORS_ORIGINS", "*")

    # LuxStudio API (for cross-service calls)
    luxstudio_api_url: str = os.getenv("LUXSTUDIO_API_URL", "http://luxstudio-backend:8750")

    # Redis
    redis_url: str = os.getenv("REDIS_URL", "")


settings = Settings()
