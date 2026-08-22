from functools import lru_cache
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    app_name: str = "JobsRSS"
    app_version: str = "2.0.0-beta"
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
    llm_timeout_seconds: int = 30
    llm_verify_tls: bool = True
    llm_rerank_interval_minutes: int = 30
    llm_max_jobs_per_run: int = 60
    llm_min_rule_score: float = 20
    llm_only_unscored: bool = True
    llm_target_profile: str = (
        "Senior cybersecurity roles focused on cloud security, application security, "
        "IAM/PAM, SOC/SIEM, threat detection, vulnerability management, and "
        "security architecture leadership."
    )

    high_match_threshold: int = 80
    allowed_origins: List[str] = Field(default_factory=lambda: ["http://localhost:3000"])

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
    linkedin_search_urls: str = ""
    linkedin_polling_interval_minutes: int = 20
    linkedin_external_enrichment_enabled: bool = True
    linkedin_external_enrichment_timeout_seconds: int = 20
    linkedin_strict_location_filter: bool = True
    linkedin_allowed_locations: str = "Singapore,Hong Kong,Shanghai,Hangzhou"

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

    def csv_items(self, value: str) -> List[str]:
        return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
