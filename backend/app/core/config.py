"""Application configuration.

All runtime configuration is defined here and loaded from environment
variables (and, for local development, from a `.env` file). No other
module should read `os.environ` directly -- this keeps configuration
centralized and easy to reason about / mock in tests.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings.

    Values are populated from environment variables first, falling back
    to the defaults below. See `.env.example` for the full list of
    variables a deployment is expected to provide.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # General
    app_name: str = "care-ai-backend"
    env: str = "local"  # local | staging | production
    debug: bool = False

    # Logging
    log_level: str = "INFO"
    json_logs: bool = False

    # API server
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Database
    database_url: str = (
        "postgresql+asyncpg://careai:careai@localhost:5432/careai"
    )
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_echo: bool = False

    # Retell — used only by the webhook adapter layer. Tool APIs remain
    # telephony-agnostic. Leave blank locally to skip signature checks;
    # production deployments must set a real key for verification.
    retell_api_key: str | None = None
    retell_agent_id: str | None = None
    retell_llm_id: str | None = None
    retell_verify_signatures: bool = True

    # Bolna — used only by /webhooks/bolna/*. Set BOLNA_API_TOKEN to the
    # same bearer value configured as `api_token` on Bolna custom tools.
    bolna_api_token: str | None = None
    bolna_agent_id: str | None = None
    bolna_verify_auth: bool = True

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    """Return a cached `Settings` instance.

    `lru_cache` ensures the environment is only parsed once per process,
    while still allowing tests to bypass the cache via
    `get_settings.cache_clear()`.
    """

    return Settings()
