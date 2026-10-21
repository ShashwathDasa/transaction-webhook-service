"""Load application settings from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration shared by the API and worker."""
    database_url: str
    redis_url: str
    transaction_queue_name: str = "transactions"
    processing_delay_seconds: int = 30
    recovery_interval_seconds: int = 60
    stale_transaction_seconds: int = 120

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
