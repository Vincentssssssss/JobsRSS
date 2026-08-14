from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    app_name: str = "JobsRSS"
    environment: str = "development"
    database_url: str = "postgresql+psycopg2://jobsrss:jobsrss@postgres:5432/jobsrss"
    rss_base_url: str = "http://localhost:8000"

    scheduler_enabled: bool = True
    collector_default_timeout_seconds: int = 20
    collector_default_retries: int = 2

    scheduler_company_interval_minutes: int = 20
    scheduler_platform_interval_minutes: int = 20
    scheduler_linkedin_email_interval_minutes: int = 15

    high_match_threshold: int = 80
    allowed_origins: List[str] = Field(default_factory=lambda: ["http://localhost:3000"])


@lru_cache
def get_settings() -> Settings:
    return Settings()
