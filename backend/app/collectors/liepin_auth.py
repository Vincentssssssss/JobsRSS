from typing import List, Optional

from app.collectors.authenticated_playwright import AuthenticatedPlaywrightCollector
from app.collectors.base import CollectorMeta


class LiepinAuthCollector(AuthenticatedPlaywrightCollector):
    meta = CollectorMeta(
        source_name="liepin_auth",
        source_type="job_platform",
        collection_method="browser_automation",
        polling_interval_minutes=20,
        search_configuration="env:LIEPIN_SEARCH_URLS",
        parser_name="liepin-search-result-parser",
        normalization_logic="app.normalization.normalizer.normalize_job",
    )
    base_domain = "liepin.com"

    def is_enabled(self) -> bool:
        return self.settings.liepin_auth_enabled

    def get_search_urls(self) -> List[str]:
        return self.settings.csv_items(self.settings.liepin_search_urls)

    def get_storage_state_path(self) -> Optional[str]:
        return self.settings.liepin_auth_storage_state_path

    def is_job_url(self, url: str) -> bool:
        lowered = url.lower()
        return "liepin.com" in lowered and any(token in lowered for token in ["job", "position", "detail"])
