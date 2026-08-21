import time
from typing import Any, Dict, Iterable, List
from urllib.parse import urljoin

import httpx

from app.core.config import get_settings
from app.official.collectors.base import OfficialCollectorBase
from app.official.location import LocationCategory, classify_official_location
from app.official.registry import get_official_source

MICROSOFT_SEARCH_URL = "https://apply.careers.microsoft.com/api/pcsx/search"
MICROSOFT_DETAIL_URL = (
    "https://apply.careers.microsoft.com/api/pcsx/position_details"
)


class MicrosoftOfficialCollector(OfficialCollectorBase):
    def __init__(self) -> None:
        super().__init__(
            get_official_source("microsoft"),
            method="json",
            parser_name="microsoft-pcsx-json",
        )

    def fetch_raw(self) -> List[Dict[str, Any]]:
        settings = get_settings()
        jobs: List[Dict[str, Any]] = []
        page_size = 10
        with httpx.Client(
            timeout=settings.official_source_timeout_seconds,
            verify=settings.official_source_verify_tls,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
                )
            },
        ) as client:
            starts = list(
                range(
                    0,
                    settings.official_source_max_jobs_per_source,
                    page_size,
                )
            )[: settings.official_source_max_pages_per_source]
            for start in starts:
                payload = _get_json_with_backoff(
                    client,
                    MICROSOFT_SEARCH_URL,
                    params={
                        "domain": "microsoft.com",
                        "query": "",
                        "location": "Shanghai",
                        "sort_by": "timestamp",
                        "start": start,
                        "num": page_size,
                    },
                    retries=settings.collector_default_retries,
                )
                positions = payload.get("positions") or payload.get("results") or []
                if not positions:
                    break
                for item in positions:
                    position_id = str(
                        item.get("id") or item.get("position_id") or ""
                    ).strip()
                    if not position_id:
                        continue
                    detail_payload = _get_json_with_backoff(
                        client,
                        MICROSOFT_DETAIL_URL,
                        params={
                            "position_id": position_id,
                            "domain": "microsoft.com",
                        },
                        retries=settings.collector_default_retries,
                    )
                    job = parse_microsoft_position(item, detail_payload)
                    if job is not None:
                        jobs.append(job)
                if len(positions) < page_size:
                    break
        return jobs[: settings.official_source_max_jobs_per_source]


def parse_microsoft_position(
    search_item: Dict[str, Any], detail_payload: Dict[str, Any]
) -> Dict[str, Any] | None:
    detail = detail_payload.get("position") or detail_payload.get("job") or detail_payload
    source_job_id = str(
        search_item.get("id")
        or search_item.get("position_id")
        or detail.get("id")
        or ""
    ).strip()
    title = str(
        detail.get("name")
        or detail.get("title")
        or search_item.get("name")
        or search_item.get("title")
        or ""
    ).strip()
    if not source_job_id or not title:
        return None
    location = _render_locations(
        detail.get("locations")
        or detail.get("standardized_locations")
        or search_item.get("locations")
        or search_item.get("location")
    )
    location_category = classify_official_location(location)
    if location_category == LocationCategory.EXCLUDED:
        return None
    description = "\n\n".join(
        value
        for value in [
            _render_text(detail.get("job_description") or detail.get("description")),
            _render_text(
                detail.get("qualifications")
                or detail.get("minimum_qualifications")
            ),
        ]
        if value
    )
    path = (
        detail.get("positionUrl")
        or detail.get("position_url")
        or search_item.get("positionUrl")
        or f"/careers/job/{source_job_id}"
    )
    source_url = urljoin("https://apply.careers.microsoft.com/", str(path))
    posted_at = (
        detail.get("posted_ts")
        or detail.get("created_ts")
        or search_item.get("posted_ts")
        or search_item.get("created_ts")
    )
    if isinstance(posted_at, (int, float)) and posted_at > 10_000_000_000:
        posted_at = posted_at / 1000
    content_hash = OfficialCollectorBase.build_hash(
        source_job_id, title, "Microsoft", location, description, source_url
    )
    return {
        "source_job_id": source_job_id,
        "company": "Microsoft",
        "title": title,
        "location": location,
        "country": "China",
        "description": description,
        "apply_url": str(detail.get("apply_url") or source_url),
        "source_url": source_url,
        "posted_at": posted_at,
        "content_hash": content_hash,
        "location_category": location_category.value,
    }


def _render_locations(value: Any) -> str:
    if value is None:
        return "Unknown"
    values = value if isinstance(value, list) else [value]
    rendered: List[str] = []
    for item in values:
        if isinstance(item, dict):
            text = ", ".join(
                str(item.get(key))
                for key in ("city", "state", "country")
                if item.get(key)
            )
            if not text:
                text = str(item.get("name") or item.get("label") or "")
        else:
            text = str(item)
        if text:
            rendered.append(text)
    return " / ".join(dict.fromkeys(rendered)) or "Unknown"


def _render_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return "\n".join(_render_text(child) for child in value.values() if child)
    if isinstance(value, Iterable):
        return "\n".join(_render_text(child) for child in value if child)
    return str(value).strip()


def _get_json_with_backoff(
    client: httpx.Client,
    url: str,
    params: Dict[str, Any],
    retries: int,
) -> Dict[str, Any]:
    response: httpx.Response | None = None
    for attempt in range(retries + 1):
        response = client.get(url, params=params)
        if response.status_code not in {429, 500, 502, 503, 504}:
            response.raise_for_status()
            return response.json()
        if attempt < retries:
            retry_after = response.headers.get("retry-after")
            try:
                delay = min(float(retry_after), 30) if retry_after else 2 ** attempt
            except ValueError:
                delay = 2 ** attempt
            time.sleep(delay)
    assert response is not None
    response.raise_for_status()
    return {}
