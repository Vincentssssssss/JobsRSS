from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.collectors.base import BaseCollector, CollectorMeta
from app.official.location import LocationCategory
from app.official.registry import OfficialSourceSpec
from app.schemas.job import UnifiedJob


class OfficialCollectorBase(BaseCollector):
    spec: OfficialSourceSpec

    def __init__(self, spec: OfficialSourceSpec, method: str, parser_name: str) -> None:
        self.spec = spec
        self.meta = CollectorMeta(
            source_name=f"official_{spec.source_id}",
            source_type="company_site",
            collection_method=method,
            polling_interval_minutes=360,
            search_configuration=f"official-registry:{spec.source_id}",
            parser_name=parser_name,
            normalization_logic="app.normalization.normalizer.normalize_job",
        )

    def normalize(self, raw: Dict[str, Any]) -> UnifiedJob:
        now = self.now()
        posted_at = parse_source_datetime(raw.get("posted_at"))
        return UnifiedJob(
            source=self.meta.source_name,
            source_job_id=str(raw["source_job_id"]),
            company=raw.get("company") or self.spec.company,
            title=raw["title"],
            location=raw.get("location") or "Unknown",
            country=raw.get("country"),
            description=raw.get("description") or raw["title"],
            apply_url=raw.get("apply_url") or raw["source_url"],
            source_url=raw["source_url"],
            posted_at=posted_at,
            updated_at=now,
            first_seen_at=now,
            last_seen_at=now,
            content_hash=raw["content_hash"],
            status="active",
            enrichment_source=self.spec.source_id,
            location_category=raw.get(
                "location_category", LocationCategory.UNCLASSIFIED.value
            ),
        )


def parse_source_datetime(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    text = str(value).strip().replace("Z", "+00:00")
    for parser in (
        lambda: datetime.fromisoformat(text),
        lambda: datetime.strptime(text, "%B %d, %Y"),
        lambda: datetime.strptime(text, "%Y-%m-%d"),
    ):
        try:
            parsed = parser()
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
