from typing import Any, Dict, Iterable, List

import httpx
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.official.collectors.base import OfficialCollectorBase
from app.official.location import LocationCategory, classify_official_location
from app.official.registry import get_official_source

ALIBABA_ROOT = "https://campus-talent.alibaba.com"
ALIBABA_PORTAL = f"{ALIBABA_ROOT}/campus/position"
ALIBABA_CHANNEL = "new_campus_group_official_site"


class AlibabaOfficialCollector(OfficialCollectorBase):
    def __init__(self) -> None:
        super().__init__(
            get_official_source("alibaba"),
            method="json_xsrf",
            parser_name="alibaba-campus-json",
        )

    def fetch_raw(self) -> List[Dict[str, Any]]:
        settings = get_settings()
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
                "Referer": ALIBABA_PORTAL,
            },
        ) as client:
            self._bootstrap_xsrf(client)
            batches_payload = self._post(
                client,
                "/searchCondition/listBatch",
                {"channel": ALIBABA_CHANNEL, "language": "zh"},
            )
            batches = _alibaba_batches(batches_payload)
            jobs: List[Dict[str, Any]] = []
            for batch in batches[
                : settings.official_source_max_pages_per_source
            ]:
                if len(jobs) >= settings.official_source_max_jobs_per_source:
                    break
                search_payload = self._post(
                    client,
                    "/position/search",
                    {
                        "batchId": batch["id"],
                        "pageIndex": 1,
                        "pageSize": min(
                            settings.official_source_max_jobs_per_source, 100
                        ),
                        "channel": ALIBABA_CHANNEL,
                        "language": "zh",
                        "regions": "上海",
                    },
                )
                for item in (search_payload.get("content") or {}).get(
                    "datas", []
                ):
                    if len(jobs) >= settings.official_source_max_jobs_per_source:
                        break
                    position_id = item.get("id")
                    if not position_id:
                        continue
                    detail_payload = self._post(
                        client,
                        "/position/detail",
                        {"id": position_id},
                    )
                    job = parse_alibaba_position(detail_payload)
                    if job is not None:
                        jobs.append(job)
            return jobs

    def _bootstrap_xsrf(self, client: httpx.Client) -> None:
        response = client.get(ALIBABA_PORTAL)
        response.raise_for_status()
        token = client.cookies.get("XSRF-TOKEN")
        if not token:
            raise RuntimeError("Alibaba careers did not issue XSRF-TOKEN")
        client.headers["X-XSRF-TOKEN"] = token

    def _post(
        self, client: httpx.Client, path: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        response = client.post(f"{ALIBABA_ROOT}{path}", json=payload)
        if response.status_code == 403:
            self._bootstrap_xsrf(client)
            response = client.post(f"{ALIBABA_ROOT}{path}", json=payload)
        response.raise_for_status()
        return response.json()


def parse_alibaba_position(payload: Dict[str, Any]) -> Dict[str, Any] | None:
    item = payload.get("content") or {}
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
    description = "\n\n".join(
        _clean_html(str(value))
        for value in (item.get("description"), item.get("requirement"))
        if value
    )
    source_url = f"{ALIBABA_PORTAL}/{source_job_id}"
    company = "Alibaba / Alibaba Cloud"
    return {
        "source_job_id": source_job_id,
        "company": company,
        "title": title,
        "location": location,
        "country": "China",
        "description": description,
        "apply_url": source_url,
        "source_url": source_url,
        "posted_at": item.get("modifyTime") or item.get("updateTime"),
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


def _alibaba_batches(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    content = payload.get("content") or {}
    batches: Dict[str, Dict[str, Any]] = {}
    for group in ("graduate", "internship", "topTalentPlan"):
        values = content.get(group) or []
        if isinstance(values, Iterable) and not isinstance(values, (str, dict)):
            for value in values:
                if isinstance(value, dict) and value.get("id"):
                    batches[str(value["id"])] = value
    return list(batches.values())


def _clean_html(value: str) -> str:
    return BeautifulSoup(value, "html.parser").get_text("\n", strip=True)
