from typing import List, Optional

from app.collectors.authenticated_playwright import AuthenticatedPlaywrightCollector
from app.collectors.base import CollectorMeta


class Job51AuthCollector(AuthenticatedPlaywrightCollector):
    meta = CollectorMeta(
        source_name="job51_auth",
        source_type="job_platform",
        collection_method="browser_automation",
        polling_interval_minutes=20,
        search_configuration="env:JOB51_SEARCH_URLS",
        parser_name="job51-search-result-parser",
        normalization_logic="app.normalization.normalizer.normalize_job",
    )
    base_domain = "51job.com"

    def is_enabled(self) -> bool:
        return self.settings.job51_auth_enabled

    def get_search_urls(self) -> List[str]:
        return self.settings.csv_items(self.settings.job51_search_urls)

    def get_storage_state_path(self) -> Optional[str]:
        return self.settings.job51_auth_storage_state_path

    def is_job_url(self, url: str) -> bool:
        lowered = url.lower()
        return "51job.com" in lowered and any(token in lowered for token in ["job", "position", "detail"])
