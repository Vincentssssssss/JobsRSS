import re
import time
from typing import Any, Dict, Iterable, List
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.official.collectors.base import OfficialCollectorBase
from app.official.location import LocationCategory, classify_official_location
from app.official.registry import get_official_source

MICROSOFT_SEARCH_URL = "https://apply.careers.microsoft.com/api/pcsx/search"
MICROSOFT_DETAIL_URL = (
    "https://apply.careers.microsoft.com/api/pcsx/position_details"
)
MICROSOFT_APPLY_ORIGIN = "https://apply.careers.microsoft.com"
_MICROSOFT_CAREER_HOSTS = {
    "apply.careers.microsoft.com",
    "jobs.careers.microsoft.com",
    "careers.microsoft.com",
    "www.careers.microsoft.com",
}
_JOB_ID_IN_PATH = re.compile(r"/job/(\d+)")


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
                positions = extract_microsoft_positions(payload)
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


def extract_microsoft_positions(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    record = _pcsx_search_record(payload)
    positions = record.get("positions") or record.get("results") or []
    return positions if isinstance(positions, list) else []


def parse_microsoft_position(
    search_item: Dict[str, Any], detail_payload: Dict[str, Any]
) -> Dict[str, Any] | None:
    detail = _pcsx_job_record(detail_payload)
    source_job_id = str(
        _coalesce(
            search_item.get("id"),
            search_item.get("position_id"),
            detail.get("id"),
        )
        or ""
    ).strip()
    title = str(
        _coalesce(
            detail.get("name"),
            detail.get("title"),
            search_item.get("name"),
            search_item.get("title"),
        )
        or ""
    ).strip()
    if not source_job_id or not title:
        return None
    location = _render_locations(
        _coalesce(
            detail.get("standardizedLocations"),
            detail.get("standardized_locations"),
            detail.get("locations"),
            search_item.get("standardizedLocations"),
            search_item.get("standardized_locations"),
            search_item.get("locations"),
            search_item.get("location"),
            detail.get("location"),
        )
    )
    location_category = classify_official_location(location)
    if location_category == LocationCategory.EXCLUDED:
        return None
    description = "\n\n".join(
        value
        for value in [
            _render_html_or_text(
                _coalesce(
                    detail.get("jobDescription"),
                    detail.get("job_description"),
                    detail.get("description"),
                )
            ),
            _render_html_or_text(
                _coalesce(
                    detail.get("qualifications"),
                    detail.get("minimum_qualifications"),
                )
            ),
        ]
        if value
    )
    source_url = build_microsoft_job_url(source_job_id, detail, search_item)
    apply_url = str(
        _coalesce(
            detail.get("applyUrl"),
            detail.get("apply_url"),
            source_url,
        )
        or source_url
    )
    if is_microsoft_career_homepage(apply_url):
        apply_url = source_url
    posted_at = _coalesce(
        detail.get("postedTs"),
        detail.get("posted_ts"),
        detail.get("creationTs"),
        detail.get("created_ts"),
        search_item.get("postedTs"),
        search_item.get("posted_ts"),
        search_item.get("creationTs"),
        search_item.get("created_ts"),
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
        "apply_url": apply_url,
        "source_url": source_url,
        "posted_at": posted_at,
        "content_hash": content_hash,
        "location_category": location_category.value,
    }


def build_microsoft_job_url(
    source_job_id: str, *records: Dict[str, Any]
) -> str:
    candidates: List[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        for key in (
            "publicUrl",
            "public_url",
            "positionUrl",
            "position_url",
        ):
            value = record.get(key)
            if value:
                candidates.append(str(value).strip())
    for candidate in candidates:
        resolved = _absolute_microsoft_url(candidate)
        if is_microsoft_job_detail_url(resolved):
            return resolved
    return f"{MICROSOFT_APPLY_ORIGIN}/careers/job/{source_job_id}"


def is_microsoft_job_detail_url(url: str) -> bool:
    parsed = _parse_url(url)
    if parsed is None:
        return False
    host = (parsed.hostname or "").lower()
    if host not in _MICROSOFT_CAREER_HOSTS:
        return False
    if _JOB_ID_IN_PATH.search(parsed.path or ""):
        return True
    query = parse_qs(parsed.query or "")
    pid = (query.get("pid") or query.get("position_id") or [""])[0]
    return bool(re.fullmatch(r"\d+", str(pid)))


def is_microsoft_career_homepage(url: str) -> bool:
    parsed = _parse_url(url)
    if parsed is None:
        return False
    host = (parsed.hostname or "").lower()
    if host not in _MICROSOFT_CAREER_HOSTS:
        return False
    return not is_microsoft_job_detail_url(url)


def _absolute_microsoft_url(value: str) -> str:
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return urljoin(f"{MICROSOFT_APPLY_ORIGIN}/", value)


def _parse_url(url: str):
    if not url:
        return None
    try:
        return urlparse(url)
    except ValueError:
        return None


def _pcsx_search_record(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    if isinstance(data, dict) and (
        isinstance(data.get("positions"), list)
        or isinstance(data.get("results"), list)
    ):
        return data
    return payload


def _pcsx_job_record(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    if isinstance(data, dict) and not isinstance(data.get("positions"), list):
        if any(
            key in data
            for key in (
                "id",
                "name",
                "jobDescription",
                "publicUrl",
                "positionUrl",
            )
        ):
            return data
    return payload.get("position") or payload.get("job") or payload


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


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


def _render_html_or_text(value: Any) -> str:
    text = _render_text(value)
    if "<" in text and ">" in text:
        return BeautifulSoup(text, "html.parser").get_text("\n", strip=True)
    return text


def _render_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return "\n".join(_render_text(child) for child in value.values() if child)
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
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
            payload = response.json()
            return payload if isinstance(payload, dict) else {}
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
