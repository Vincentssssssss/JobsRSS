from typing import Any, List, Optional

from app.collectors.authenticated_playwright import AuthenticatedPlaywrightCollector
from app.collectors.base import CollectorMeta


class LinkedInAuthCollector(AuthenticatedPlaywrightCollector):
    meta = CollectorMeta(
        source_name="linkedin_auth",
        source_type="job_platform",
        collection_method="browser_automation",
        polling_interval_minutes=20,
        search_configuration="env:LINKEDIN_SEARCH_URLS",
        parser_name="linkedin-search-result-parser",
        normalization_logic="app.normalization.normalizer.normalize_job",
    )
    base_domain = "linkedin.com"

    def is_enabled(self) -> bool:
        return self.settings.linkedin_auth_enabled

    def get_search_urls(self) -> List[str]:
        return self.settings.csv_items(self.settings.linkedin_search_urls)

    def get_storage_state_path(self) -> Optional[str]:
        return self.settings.linkedin_auth_storage_state_path

    def perform_login(self, page: Any) -> None:
        if not self.settings.linkedin_auth_username or not self.settings.linkedin_auth_password:
            return
        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=45000)
        page.fill("#username", self.settings.linkedin_auth_username)
        page.fill("#password", self.settings.linkedin_auth_password)
        page.click("button[type='submit']")
        page.wait_for_timeout(3000)

    def is_job_url(self, url: str) -> bool:
        lowered = url.lower()
        return "linkedin.com/jobs/view/" in lowered or "linkedin.com/jobs/search/" in lowered
