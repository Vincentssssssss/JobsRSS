from typing import Any, Dict, List

import httpx

from app.core.config import get_settings
from app.official.collectors.base import OfficialCollectorBase
from app.official.location import LocationCategory, classify_official_location
from app.official.registry import get_official_source

HOTJOB_ROOT = "https://wecruit.hotjob.cn"
YUNNAN_BAIYAO_TENANT = "SU6136b970bef57c3b638162c4"
SIMCERE_TENANT = "SU61458d83bef57c54dcb4e43f"


class HotJobOfficialCollector(OfficialCollectorBase):
    def __init__(
        self,
        source_id: str,
        company: str,
        tenant: str,
        api_root: str = HOTJOB_ROOT,
    ) -> None:
        super().__init__(
            get_official_source(source_id),
            method="json",
            parser_name="hotjob-json",
        )
        self.company = company
        self.tenant = tenant
        self.api_root = api_root.rstrip("/")

    def fetch_raw(self) -> List[Dict[str, Any]]:
        settings = get_settings()
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": f"{self.api_root}/{self.tenant}/pb/social.html",
        }
        jobs: List[Dict[str, Any]] = []
        with httpx.Client(
            timeout=settings.official_source_timeout_seconds,
            verify=settings.official_source_verify_tls,
            headers=headers,
        ) as client:
            first = self._list_page(client, 1)
            page_form = (first.get("data") or {}).get("pageForm") or {}
            total_pages = min(
                int(page_form.get("totalPage") or 1),
                settings.official_source_max_pages_per_source,
            )
            pages = [first]
            for page in range(2, total_pages + 1):
                pages.append(self._list_page(client, page))
            for payload in pages:
                items = (
                    (payload.get("data") or {})
                    .get("pageForm", {})
                    .get("pageData", [])
                )
                for item in items:
                    category = classify_official_location(
                        str(item.get("workPlaceStr") or "")
                    )
                    if category == LocationCategory.EXCLUDED:
                        continue
                    detail = client.post(
                        (
                            f"{self.api_root}/wecruit/positionInfo/"
                            f"listPositionDetail/{self.tenant}"
                        ),
                        data={
                            "postId": item.get("postId"),
                            "recruitType": "2",
                            "isFrompb": "true",
                        },
                    )
                    detail.raise_for_status()
                    job = parse_hotjob_detail(
                        detail.json(),
                        company_fallback=self.company,
                        tenant=self.tenant,
                        api_root=self.api_root,
                    )
                    if job is not None:
                        jobs.append(job)
                    if len(jobs) >= settings.official_source_max_jobs_per_source:
                        return jobs
        return jobs

    def _list_page(
        self, client: httpx.Client, page: int
    ) -> Dict[str, Any]:
        response = client.post(
            (
                f"{self.api_root}/wecruit/positionInfo/"
                f"listPosition/{self.tenant}"
            ),
            data={
                "isFrompb": "true",
                "recruitType": "2",
                "pageSize": "50",
                "currentPage": str(page),
            },
        )
        response.raise_for_status()
        return response.json()


class YunnanBaiyaoOfficialCollector(HotJobOfficialCollector):
    def __init__(self) -> None:
        super().__init__(
            source_id="yunnan_baiyao",
            company="Yunnan Baiyao / 云南白药",
            tenant=YUNNAN_BAIYAO_TENANT,
        )


class SimcereOfficialCollector(HotJobOfficialCollector):
    def __init__(self) -> None:
        super().__init__(
            source_id="simcere",
            company="Simcere / 先声药业",
            tenant=SIMCERE_TENANT,
        )


class DeloitteOfficialCollector(HotJobOfficialCollector):
    def __init__(self) -> None:
        super().__init__(
            source_id="deloitte",
            company="Deloitte / 德勤",
            tenant="SU649e304a6a9f0ef690533e9a",
            api_root="https://ehjobs.deloitte.com.cn",
        )


def parse_hotjob_detail(
    payload: Dict[str, Any],
    *,
    company_fallback: str = "Yunnan Baiyao / 云南白药",
    tenant: str = YUNNAN_BAIYAO_TENANT,
    api_root: str = HOTJOB_ROOT,
) -> Dict[str, Any] | None:
    item = payload.get("data") or {}
    source_job_id = str(item.get("postId") or "").strip()
    title = str(item.get("postName") or "").strip()
    if not source_job_id or not title:
        return None
    location = str(item.get("workPlaceStr") or "Unknown")
    category = classify_official_location(location)
    if category == LocationCategory.EXCLUDED:
        return None
    description = "\n\n".join(
        str(value).strip()
        for value in (
            item.get("workContent"),
            item.get("serviceCondition"),
        )
        if value
    )
    company = str(item.get("company") or company_fallback)
    source_url = (
        f"{api_root.rstrip('/')}/{tenant}/pb/"
        f"posDetail.html?postId={source_job_id}"
    )
    return {
        "source_job_id": source_job_id,
        "company": company,
        "title": title,
        "location": location,
        "country": "China",
        "description": description,
        "apply_url": source_url,
        "source_url": source_url,
        "posted_at": item.get("publishDate") or item.get("publishFirstDate"),
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
