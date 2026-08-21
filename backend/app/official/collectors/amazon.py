import json
from typing import Any, Dict, List
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.official.collectors.base import OfficialCollectorBase
from app.official.location import LocationCategory, classify_official_location
from app.official.registry import get_official_source

AMAZON_SEARCH_URL = "https://www.amazon.jobs/en/search.json"


class AmazonOfficialCollector(OfficialCollectorBase):
    def __init__(self) -> None:
        super().__init__(
            get_official_source("amazon_aws"),
            method="json",
            parser_name="amazon-jobs-json",
        )

    def fetch_raw(self) -> List[Dict[str, Any]]:
        settings = get_settings()
        jobs: List[Dict[str, Any]] = []
        page_size = 10
        with httpx.Client(
            timeout=settings.official_source_timeout_seconds,
            verify=settings.official_source_verify_tls,
            headers={"User-Agent": "JobsRSS/2.0 (+personal job monitor)"},
        ) as client:
            for offset in range(0, settings.official_source_max_jobs_per_source, page_size):
                response = client.get(
                    AMAZON_SEARCH_URL,
                    params={
                        "country": "CHN",
                        "city": "Shanghai",
                        "offset": offset,
                        "result_limit": page_size,
                        "sort": "recent",
                    },
                )
                response.raise_for_status()
                parsed = parse_amazon_jobs(response.json())
                jobs.extend(parsed)
                if len(parsed) < page_size:
                    break
        return jobs[: settings.official_source_max_jobs_per_source]


def parse_amazon_jobs(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    parsed: List[Dict[str, Any]] = []
    for item in payload.get("jobs", []):
        source_job_id = str(item.get("id_icims") or item.get("id") or "").strip()
        title = str(item.get("title") or "").strip()
        if not source_job_id or not title:
            continue
        location = _amazon_location(item)
        location_category = classify_official_location(location)
        if location_category == LocationCategory.EXCLUDED:
            continue
        description_parts = [
            item.get("description"),
            item.get("basic_qualifications"),
            item.get("preferred_qualifications"),
        ]
        description = "\n\n".join(
            _clean_html(str(part)) for part in description_parts if part
        )
        source_url = urljoin(
            "https://www.amazon.jobs/",
            str(item.get("job_path") or item.get("url") or ""),
        )
        company = str(item.get("company_name") or item.get("company") or "Amazon / AWS")
        content_hash = OfficialCollectorBase.build_hash(
            source_job_id, title, company, location, description, source_url
        )
        parsed.append(
            {
                "source_job_id": source_job_id,
                "company": company,
                "title": title,
                "location": location,
                "country": "China",
                "description": description,
                "apply_url": str(item.get("apply_url") or source_url),
                "source_url": source_url,
                "posted_at": item.get("posted_date") or item.get("updated_time"),
                "content_hash": content_hash,
                "location_category": location_category.value,
            }
        )
    return parsed


def _amazon_location(item: Dict[str, Any]) -> str:
    values: List[str] = []
    for key in ("locations", "normalized_location", "location", "city"):
        raw = item.get(key)
        if not raw:
            continue
        if isinstance(raw, str) and raw.startswith("["):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                pass
        if isinstance(raw, list):
            values.extend(str(value) for value in raw if value)
        elif isinstance(raw, dict):
            values.extend(str(value) for value in raw.values() if value)
        else:
            values.append(str(raw))
    return " / ".join(dict.fromkeys(values)) or "Unknown"


def _clean_html(value: str) -> str:
    return BeautifulSoup(value, "html.parser").get_text("\n", strip=True)
