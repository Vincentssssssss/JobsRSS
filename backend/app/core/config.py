import json
from functools import lru_cache
from typing import Annotated, List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    app_name: str = "JobsRSS"
    app_version: str = "2.0.0"
    environment: str = "development"
    database_url: str = "postgresql+psycopg2://jobsrss:jobsrss@postgres:5432/jobsrss"
    rss_base_url: str = "http://localhost:8000"

    scheduler_enabled: bool = True
    collector_default_timeout_seconds: int = 20
    collector_default_retries: int = 2

    scheduler_company_interval_minutes: int = 20
    scheduler_platform_interval_minutes: int = 20
    scheduler_linkedin_email_interval_minutes: int = 15
    scheduler_linkedin_email_max_messages: int = 30
    scheduler_digest_hour_utc: int = 1
    scheduler_digest_minute_utc: int = 0
    official_sources_enabled: bool = True
    official_source_interval_minutes: int = 360
    official_source_timeout_seconds: int = 30
    official_source_max_jobs_per_source: int = 50
    official_source_max_pages_per_source: int = 10
    official_source_stale_after_days: int = 30
    official_source_verify_tls: bool = True
    llm_rerank_enabled: bool = False
    llm_provider: str = "openai"
    llm_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_api_version: Optional[str] = None
    llm_azure_use_default_credential: bool = False
    llm_azure_scope: str = "https://ai.azure.com/.default"
    llm_model: str = "gpt-4o-mini"
    llm_temperature: Optional[float] = None
    llm_timeout_seconds: int = 30
    llm_verify_tls: bool = True
    llm_request_max_retries: int = 2
    llm_request_retry_backoff_seconds: float = 1.5
    llm_abort_after_consecutive_failures: int = 8
    llm_rerank_interval_minutes: int = 30
    llm_max_jobs_per_run: int = 60
    llm_min_rule_score: float = 20
    llm_only_unscored: bool = True
    llm_reject_early_career: bool = True
    llm_target_profile: str = (
        "Senior cybersecurity roles focused on cloud security, application security, "
        "IAM/PAM, SOC/SIEM, threat detection, vulnerability management, and "
        "security architecture leadership across Shanghai/Jiangsu/Zhejiang "
        "(Yangtze River Delta), Hong Kong, and Singapore."
    )

    high_match_threshold: int = 80
    allowed_origins: Annotated[List[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )

    linkedin_email_enabled: bool = False
    linkedin_email_imap_host: Optional[str] = None
    linkedin_email_imap_port: int = 993
    linkedin_email_username: Optional[str] = None
    linkedin_email_password: Optional[str] = None
    linkedin_email_folder: str = "INBOX"
    linkedin_email_sender_filter: str = "jobs-noreply@linkedin.com"

    linkedin_auth_enabled: bool = False
    linkedin_auth_username: Optional[str] = None
    linkedin_auth_password: Optional[str] = None
    linkedin_auth_storage_state_path: Optional[str] = None
    linkedin_require_storage_state: bool = True
    linkedin_search_urls: str = ""
    linkedin_polling_interval_minutes: int = 20
    linkedin_auth_stale_after_days: int = 14
    linkedin_external_enrichment_enabled: bool = True
    linkedin_external_enrichment_timeout_seconds: int = 20
    linkedin_strict_location_filter: bool = True
    linkedin_allowed_locations: str = "Singapore,Hong Kong,Shanghai,Jiangsu,Zhejiang"

    job51_auth_enabled: bool = False
    job51_auth_username: Optional[str] = None
    job51_auth_password: Optional[str] = None
    job51_auth_storage_state_path: Optional[str] = None
    job51_search_urls: str = ""
    job51_polling_interval_minutes: int = 20

    liepin_auth_enabled: bool = False
    liepin_auth_username: Optional[str] = None
    liepin_auth_password: Optional[str] = None
    liepin_auth_storage_state_path: Optional[str] = None
    liepin_search_urls: str = ""
    liepin_polling_interval_minutes: int = 20

    digest_email_enabled: bool = False
    digest_email_smtp_host: Optional[str] = None
    digest_email_smtp_port: int = 587
    digest_email_smtp_username: Optional[str] = None
    digest_email_smtp_password: Optional[str] = None
    digest_email_sender: Optional[str] = None
    digest_email_recipients: str = ""
    digest_email_use_tls: bool = True

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: object) -> object:
        if isinstance(value, list):
            return value
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
        return [item.strip() for item in text.split(",") if item.strip()]

    def csv_items(self, value: str) -> List[str]:
        return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
