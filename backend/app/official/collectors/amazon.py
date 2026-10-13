import json
from typing import Any, Dict, List
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.official.collectors.base import OfficialCollectorBase, interleave_capped
from app.official.location import (
    LocationCategory,
    classify_official_location,
    country_for_category,
)
from app.official.registry import get_official_source

AMAZON_SEARCH_URL = "https://www.amazon.jobs/en/search.json"
AMAZON_PAGE_SIZE = 100
AMAZON_LOCATION_QUERIES = (
    {"country": "CHN", "city": "Shanghai"},
    {"country": "MYS"},
)


class AmazonOfficialCollector(OfficialCollectorBase):
    def __init__(self) -> None:
        super().__init__(
            get_official_source("amazon_aws"),
            method="json",
            parser_name="amazon-jobs-json",
        )

    def fetch_raw(self) -> List[Dict[str, Any]]:
        settings = get_settings()
        limit = settings.official_source_max_jobs_per_source
        with httpx.Client(
            timeout=settings.official_source_timeout_seconds,
            verify=settings.official_source_verify_tls,
            headers={"User-Agent": "JobsRSS/2.0 (+personal job monitor)"},
        ) as client:
            groups = [
                self._search(client, query, limit, settings.official_source_max_pages_per_source)
                for query in AMAZON_LOCATION_QUERIES
            ]
        return interleave_capped(groups, limit, key=lambda job: job["source_job_id"])

    @staticmethod
    def _search(
        client: httpx.Client,
        query: Dict[str, str],
        limit: int,
        max_pages: int,
    ) -> List[Dict[str, Any]]:
        jobs: List[Dict[str, Any]] = []
        for page in range(max_pages):
            if len(jobs) >= limit:
                break
            response = client.get(
                AMAZON_SEARCH_URL,
                params={
                    **query,
                    "offset": page * AMAZON_PAGE_SIZE,
                    "result_limit": AMAZON_PAGE_SIZE,
                    "sort": "recent",
                },
            )
            response.raise_for_status()
            payload = response.json()
            jobs.extend(parse_amazon_jobs(payload))
            if len(payload.get("jobs") or []) < AMAZON_PAGE_SIZE:
                break
        return jobs


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
                "country": country_for_category(location_category),
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
    values = [
        label
        for label in (_amazon_location_label(entry) for entry in _as_list(item.get("locations")))
        if label
    ]
    if not values:
        values = [
            str(item.get(key))
            for key in ("normalized_location", "location", "city")
            if item.get(key)
        ]
    return " / ".join(dict.fromkeys(values)) or "Unknown"


def _as_list(raw: Any) -> List[Any]:
    if not raw:
        return []
    if isinstance(raw, str) and raw.startswith("["):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return [raw]
    return raw if isinstance(raw, list) else [raw]


def _amazon_location_label(entry: Any) -> str:
    # Live search results encode each location as a JSON object string.
    if isinstance(entry, str) and entry.lstrip().startswith("{"):
        try:
            entry = json.loads(entry)
        except json.JSONDecodeError:
            return entry.strip()
    if isinstance(entry, dict):
        return str(
            entry.get("normalizedLocation")
            or entry.get("location")
            or ", ".join(
                str(entry[key]) for key in ("city", "normalizedCountryName") if entry.get(key)
            )
        ).strip()
    return str(entry).strip()


def _clean_html(value: str) -> str:
    return BeautifulSoup(value, "html.parser").get_text("\n", strip=True)
