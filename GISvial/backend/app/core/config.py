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
    gis_internal_api_url: str = os.getenv("GIS_INTERNAL_API_URL", "http://gisvial-backend:8733")
    oidc_token_url: str = os.getenv("OIDC_TOKEN_URL", "")
    lux_worker_client_id: str = os.getenv("LUX_WORKER_CLIENT_ID", "gisvial-worker")
    lux_worker_client_secret: str = os.getenv("LUX_WORKER_CLIENT_SECRET", "gisvial-worker-secret")
    lux_worker_id: str = os.getenv("LUX_WORKER_ID", "gisvial-worker")
    lux_worker_timeout_seconds: float = float(os.getenv("LUX_WORKER_TIMEOUT_SECONDS", "90"))
    lux_job_lease_seconds: int = int(os.getenv("LUX_JOB_LEASE_SECONDS", "120"))
    lux_job_poll_seconds: float = float(os.getenv("LUX_JOB_POLL_SECONDS", "1"))
    lux_job_enabled: bool = os.getenv("LUX_JOB_ENABLED", "true").lower() == "true"
    oidc_audiences: tuple[str, ...] = tuple(
        value.strip() for value in os.getenv("OIDC_AUDIENCES", "").split(",") if value.strip()
    )
    oidc_allowed_clients: tuple[str, ...] = tuple(
        value.strip() for value in os.getenv(
            "OIDC_ALLOWED_CLIENTS", "portal,gisvial,gateway,gisvial-worker",
        ).split(",") if value.strip()
    )

    # Redis
    redis_url: str = os.getenv("REDIS_URL", "")


settings = Settings()
