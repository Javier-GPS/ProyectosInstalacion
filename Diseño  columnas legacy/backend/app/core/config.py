"""
Salvi Studio · Columns — Configuración central
Separación estricta entre configuración técnica, funcional y secretos (P-03).
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, PostgresDsn


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Aplicación ──────────────────────────────────────────────────────────
    app_name: str = "Salvi Studio · Columns"
    app_version: str = "0.1.0"
    environment: str = Field(default="development", pattern="^(development|integration|staging|production)$")
    debug: bool = False

    # ── Base de datos ────────────────────────────────────────────────────────
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://salvi:salvi@localhost:5432/salvi_columns"
    )
    database_url_sync: str = Field(
        default="postgresql+psycopg2://salvi:salvi@localhost:5432/salvi_columns"
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # ── Redis / Cola de trabajos ─────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Almacenamiento de objetos (S3 / MinIO) ───────────────────────────────
    storage_endpoint: str = "http://localhost:9000"
    storage_access_key: str = "minioadmin"
    storage_secret_key: str = "minioadmin"
    storage_bucket: str = "salvi-columns"
    storage_region: str = "eu-west-1"

    # ── Seguridad / JWT ──────────────────────────────────────────────────────
    secret_key: str = Field(default="CHANGE_IN_PRODUCTION_32_chars_min")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    # ── Unidades (P-06: almacenamiento interno en SI) ────────────────────────
    internal_unit_system: str = "SI"

    # ── Auditoría ────────────────────────────────────────────────────────────
    audit_retention_years: int = 10

    # ── SLOs (referencia) ────────────────────────────────────────────────────
    slo_read_latency_p95_ms: int = 2000
    slo_error_rate_max_pct: float = 1.0

    # ── Feature flags ────────────────────────────────────────────────────────
    feature_m4_liberation: bool = False       # M4 se implementa en Fase 15
    feature_catenary_calc: bool = False       # Catenarias automáticas en Fase 17
    feature_solidworks_api: bool = False      # Integración nativa en Fase 18
    feature_external_collab: bool = False     # Colaboración externa desactivada inicialmente


settings = Settings()
