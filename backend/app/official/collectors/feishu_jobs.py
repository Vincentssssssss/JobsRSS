from typing import Any, Dict, List
from urllib.parse import urljoin

import httpx

from app.core.config import get_settings
from app.official.collectors.base import OfficialCollectorBase
from app.official.location import LocationCategory, classify_official_location
from app.official.registry import get_official_source


class FeishuJobsOfficialCollector(OfficialCollectorBase):
    def __init__(
        self,
        source_id: str,
        api_root: str,
        company: str,
        recruitment_id: str,
        headers: Dict[str, str],
        detail_path: str,
    ) -> None:
        super().__init__(
            get_official_source(source_id),
            method="json",
            parser_name="feishu-recruiting-json",
        )
        self.api_root = api_root
        self.company = company
        self.recruitment_id = recruitment_id
        self.portal_headers = headers
        self.detail_path = detail_path

    def fetch_raw(self) -> List[Dict[str, Any]]:
        settings = get_settings()
        jobs: List[Dict[str, Any]] = []
        page_size = min(settings.official_source_max_jobs_per_source, 100)
        with httpx.Client(
            timeout=settings.official_source_timeout_seconds,
            verify=settings.official_source_verify_tls,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
                ),
                "Origin": self.api_root,
                "Referer": f"{self.api_root}/",
                "portal-platform": "pc",
                **self.portal_headers,
            },
        ) as client:
            offsets = list(
                range(
                    0,
                    settings.official_source_max_jobs_per_source,
                    page_size,
                )
            )[: settings.official_source_max_pages_per_source]
            for offset in offsets:
                response = client.post(
                    urljoin(self.api_root, "/api/v1/search/job/posts"),
                    json={
                        "keyword": "",
                        "limit": page_size,
                        "offset": offset,
                        "portal_type": 3,
                        "portal_entrance": 1,
                        "language": "zh",
                        "recruitment_id_list": [self.recruitment_id],
                        "location_code_list": ["CT_125"],
                    },
                )
                response.raise_for_status()
                parsed = parse_feishu_jobs(
                    response.json(),
                    company=self.company,
                    source_root=self.api_root,
                    detail_path=self.detail_path,
                )
                jobs.extend(parsed)
                if len(parsed) < page_size:
                    break
        return jobs[: settings.official_source_max_jobs_per_source]


class XiaomiOfficialCollector(FeishuJobsOfficialCollector):
    def __init__(self) -> None:
        super().__init__(
            source_id="xiaomi",
            api_root="https://xiaomi.jobs.f.mioffice.cn",
            company="Xiaomi",
            recruitment_id="201",
            headers={
                "portal-channel": "campus",
                "website-path": "campus",
            },
            detail_path="/campus/position/{id}/detail",
        )


class ByteDanceOfficialCollector(FeishuJobsOfficialCollector):
    def __init__(self) -> None:
        super().__init__(
            source_id="bytedance",
            api_root="https://jobs.bytedance.com",
            company="ByteDance",
            recruitment_id="101",
            headers={
                "portal-channel": "society",
                "website-path": "society",
            },
            detail_path="/experienced/position/{id}/detail",
        )


def parse_feishu_jobs(
    payload: Dict[str, Any],
    company: str,
    source_root: str,
    detail_path: str,
) -> List[Dict[str, Any]]:
    data = payload.get("data") or payload.get("Data") or {}
    items = (
        data.get("job_post_list")
        or data.get("jobPostList")
        or data.get("posts")
        or []
    )
    jobs: List[Dict[str, Any]] = []
    for item in items:
        source_job_id = str(
            item.get("id") or item.get("post_id") or item.get("job_post_id") or ""
        ).strip()
        title = str(item.get("title") or item.get("name") or "").strip()
        if not source_job_id or not title:
            continue
        location = _render_locations(
            item.get("location_list")
            or item.get("locationList")
            or item.get("city_list")
            or item.get("city_info")
            or item.get("city")
        )
        category = classify_official_location(location)
        if category == LocationCategory.EXCLUDED:
            continue
        description = "\n\n".join(
            str(value).strip()
            for value in (
                item.get("description") or item.get("job_description"),
                item.get("requirement") or item.get("job_requirement"),
            )
            if value
        )
        source_url = urljoin(
            source_root,
            detail_path.format(id=source_job_id),
        )
        jobs.append(
            {
                "source_job_id": source_job_id,
                "company": company,
                "title": title,
                "location": location,
                "country": "China",
                "description": description,
                "apply_url": source_url,
                "source_url": source_url,
                "posted_at": item.get("publish_time")
                or item.get("publishTime"),
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
        )
    return jobs


def _render_locations(value: Any) -> str:
    if value is None:
        return "Unknown"
    values = value if isinstance(value, list) else [value]
    rendered: List[str] = []
    for item in values:
        if isinstance(item, dict):
            text = str(
                item.get("name")
                or item.get("city_name")
                or item.get("location_name")
                or ""
            )
        else:
            text = str(item)
        if text:
            rendered.append(text)
    return " / ".join(dict.fromkeys(rendered)) or "Unknown"
