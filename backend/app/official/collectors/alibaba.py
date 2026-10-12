from typing import Any, Dict, List

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

ALIBABA_ROOT = "https://talent.alibaba.com"
ALIBABA_CAMPUS_ROOT = "https://campus-talent.alibaba.com"
ALIBABA_PAGE_SIZE = 100
# (language, channel, keyword). The social portal lists ~4,000 roles with no
# function filter, so a keyword search keeps the security roles instead of the
# newest N postings across all of Alibaba. Location is filtered client-side
# because many roles list several cities.
ALIBABA_SOCIAL_SEARCHES = (
    ("zh", "group_official_site", "安全"),
    ("zh", "group_official_site", "security"),
    ("en", "group_overseas_official_site", "security"),
)


class AlibabaOfficialCollector(OfficialCollectorBase):
    retired_source_url_prefixes = (ALIBABA_CAMPUS_ROOT,)

    def __init__(self) -> None:
        super().__init__(
            get_official_source("alibaba"),
            method="json_xsrf",
            parser_name="alibaba-social-json",
        )

    def fetch_raw(self) -> List[Dict[str, Any]]:
        settings = get_settings()
        limit = settings.official_source_max_jobs_per_source
        with httpx.Client(
            timeout=settings.official_source_timeout_seconds,
            verify=settings.official_source_verify_tls,
            follow_redirects=False,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
                ),
                "Accept": "application/json",
            },
        ) as client:
            groups = [
                self._search(
                    client,
                    language,
                    channel,
                    keyword,
                    limit=limit,
                    max_pages=settings.official_source_max_pages_per_source,
                )
                for language, channel, keyword in ALIBABA_SOCIAL_SEARCHES
            ]
        return interleave_capped(groups, limit, key=lambda job: job["source_job_id"])

    def _search(
        self,
        client: httpx.Client,
        language: str,
        channel: str,
        keyword: str,
        *,
        limit: int,
        max_pages: int,
    ) -> List[Dict[str, Any]]:
        jobs: List[Dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            if len(jobs) >= limit:
                break
            payload = self._post_search(
                client,
                language,
                {
                    "channel": channel,
                    "language": language,
                    "key": keyword,
                    "pageIndex": page,
                    "pageSize": ALIBABA_PAGE_SIZE,
                },
            )
            items = (payload.get("content") or {}).get("datas") or []
            for item in items:
                job = parse_alibaba_position(item, language=language)
                if job is not None:
                    jobs.append(job)
            if len(items) < ALIBABA_PAGE_SIZE:
                break
        return jobs

    def _bootstrap_xsrf(self, client: httpx.Client, language: str) -> None:
        # The portal answers with a 302 that still sets the XSRF cookie.
        response = client.get(alibaba_portal_url(language))
        token = client.cookies.get("XSRF-TOKEN")
        if response.status_code >= 400 or not token:
            raise RuntimeError("Alibaba careers did not issue XSRF-TOKEN")
        client.headers["X-XSRF-TOKEN"] = token

    def _post_search(
        self, client: httpx.Client, language: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        if "X-XSRF-TOKEN" not in client.headers:
            self._bootstrap_xsrf(client, language)
        headers = {"Referer": alibaba_portal_url(language)}
        url = f"{ALIBABA_ROOT}/position/search"
        response = client.post(url, json=payload, headers=headers)
        if response.status_code == 403:
            self._bootstrap_xsrf(client, language)
            response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        body = response.json()
        if body.get("success") is False:
            raise RuntimeError(
                f"Alibaba position search failed: {body.get('errorMsg') or body.get('errorCode')}"
            )
        return body


def alibaba_portal_url(language: str) -> str:
    return f"{ALIBABA_ROOT}/off-campus/position-list?lang={language}"


def alibaba_position_url(position_id: str, language: str) -> str:
    prefix = "/en" if language == "en" else ""
    return f"{ALIBABA_ROOT}{prefix}/off-campus/position-detail?positionId={position_id}"


def parse_alibaba_position(
    item: Dict[str, Any], *, language: str = "zh"
) -> Dict[str, Any] | None:
    source_job_id = str(item.get("id") or "").strip()
    title = str(item.get("name") or "").strip()
    if not source_job_id or not title:
        return None
    locations = item.get("workLocations") or []
    location = " / ".join(
        str(value.get("name") or value.get("label") or "")
        if isinstance(value, dict)
        else str(value)
        for value in locations
        if value
    ) or "Unknown"
    category = classify_official_location(location)
    if category == LocationCategory.EXCLUDED:
        return None
    body_sections = [
        _clean_html(str(value))
        for value in (item.get("description"), item.get("requirement"))
        if value
    ]
    metadata_lines = _build_alibaba_metadata_lines(item)
    if metadata_lines:
        body_sections.append("\n".join(metadata_lines))
    description = "\n\n".join(section for section in body_sections if section)
    source_url = alibaba_position_url(source_job_id, language)
    company = "Alibaba / Alibaba Cloud"
    return {
        "source_job_id": source_job_id,
        "company": company,
        "title": title,
        "location": location,
        "country": country_for_category(category),
        "description": description,
        "apply_url": source_url,
        "source_url": source_url,
        "posted_at": item.get("publishTime") or item.get("modifyTime"),
        "content_hash": OfficialCollectorBase.build_hash(
            source_job_id,
            title,
            company,
            location,
            description,
            source_url,
        ),
        "location_category": category.value,
    }


def _clean_html(value: str) -> str:
    return BeautifulSoup(value, "html.parser").get_text("\n", strip=True)


def _build_alibaba_metadata_lines(item: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    experience = _format_experience(item.get("experience"))
    if experience:
        lines.append(f"Experience: {experience}")
    for label, raw_value in (
        ("Category", item.get("categoryName")),
        ("Department", item.get("department")),
    ):
        value = raw_value.strip() if isinstance(raw_value, str) else ""
        if value:
            lines.append(f"{label}: {value}")
    return lines


def _format_experience(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    low, high = value.get("from"), value.get("to")
    if low and high:
        return f"{low}-{high} years"
    if low:
        return f"{low}+ years"
    if high:
        return f"up to {high} years"
    return ""
