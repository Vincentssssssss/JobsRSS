from typing import Any, Dict, List

from app.collectors.base import BaseCollector, CollectorMeta
from app.schemas.job import UnifiedJob


class MicrosoftCollector(BaseCollector):
    meta = CollectorMeta(
        source_name="microsoft",
        source_type="company_site",
        collection_method="json",
        polling_interval_minutes=20,
    )

    def fetch_raw(self) -> List[Dict[str, Any]]:
        # Placeholder stub for Phase 1 skeleton.
        return [
            {
                "id": "msft-demo-001",
                "company": "Microsoft",
                "title": "Cloud Security Architect",
                "location": "Hong Kong",
                "country": "Hong Kong",
                "description": "Lead cloud security architecture and DevSecOps practices.",
                "apply_url": "https://careers.microsoft.com/",
                "source_url": "https://careers.microsoft.com/",
            }
        ]

    def normalize(self, raw: Dict[str, Any]) -> UnifiedJob:
        content_hash = self.build_hash(raw["id"], raw["title"], raw["location"], raw["description"])
        now = self.now()
        return UnifiedJob(
            source=self.meta.source_name,
            source_job_id=raw["id"],
            company=raw["company"],
            title=raw["title"],
            location=raw["location"],
            country=raw.get("country"),
            description=raw["description"],
            apply_url=raw["apply_url"],
            source_url=raw["source_url"],
            posted_at=now,
            updated_at=now,
            first_seen_at=now,
            last_seen_at=now,
            content_hash=content_hash,
            status="active",
        )
