import math
from typing import Any, Dict, List

import httpx

from app.core.config import get_settings
from app.official.collectors.base import OfficialCollectorBase
from app.official.location import LocationCategory, classify_official_location
from app.official.registry import get_official_source


class BeisenOfficialCollector(OfficialCollectorBase):
    def __init__(
        self,
        source_id: str,
        company: str,
        portal_root: str,
    ) -> None:
        super().__init__(
            get_official_source(source_id),
            method="json",
            parser_name="beisen-zhiye-json",
        )
        self.company = company
        self.portal_root = portal_root

    def fetch_raw(self) -> List[Dict[str, Any]]:
        settings = get_settings()
        page_size = min(settings.official_source_max_jobs_per_source, 20)
        jobs: List[Dict[str, Any]] = []
        with httpx.Client(
            timeout=settings.official_source_timeout_seconds,
            verify=settings.official_source_verify_tls,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": f"{self.portal_root}/social/jobs",
            },
        ) as client:
            for page_index in range(
                0,
                min(
                    math.ceil(
                        settings.official_source_max_jobs_per_source / page_size
                    ),
                    settings.official_source_max_pages_per_source,
                ),
            ):
                response = client.post(
                    f"{self.portal_root}/api/Jobad/GetJobAdPageList",
                    json={
                        "PageIndex": page_index,
                        "PageSize": page_size,
                        "LocId": ["3100"],
                        "Category": ["1"],
                        "KeyWords": "",
                        "SpecialType": 0,
                        "PortalId": "",
                        "DisplayFields": [
                            "Category",
                            "Kind",
                            "LocId",
                            "PostDate",
                        ],
                    },
                )
                response.raise_for_status()
                parsed = parse_beisen_jobs(
                    response.json(),
                    company=self.company,
                    portal_root=self.portal_root,
                )
                jobs.extend(parsed)
                if len(parsed) < page_size:
                    break
        return jobs[: settings.official_source_max_jobs_per_source]


class WuXiAppTecOfficialCollector(BeisenOfficialCollector):
    def __init__(self) -> None:
        super().__init__(
            source_id="wuxi_apptec",
            company="WuXi AppTec / 药明康德",
            portal_root="https://wuxiapptec.zhiye.com",
        )


class ChiaTaiTianqingOfficialCollector(BeisenOfficialCollector):
    def __init__(self) -> None:
        super().__init__(
            source_id="ct_tianqing",
            company="Chia Tai Tianqing / 正大天晴",
            portal_root="https://cttq.zhiye.com",
        )


class InnoventOfficialCollector(BeisenOfficialCollector):
    def __init__(self) -> None:
        super().__init__(
            source_id="innovent",
            company="Innovent Biologics / 信达生物",
            portal_root="https://innoventbio.zhiye.com",
        )


def parse_beisen_jobs(
    payload: Dict[str, Any],
    company: str,
    portal_root: str,
) -> List[Dict[str, Any]]:
    jobs: List[Dict[str, Any]] = []
    for item in payload.get("Data") or payload.get("data") or []:
        source_job_id = str(
            item.get("Id") or item.get("id") or item.get("JobAdId") or ""
        ).strip()
        title = str(
            item.get("JobAdName") or item.get("jobAdName") or ""
        ).strip()
        if not source_job_id or not title:
            continue
        locations = item.get("LocNames") or item.get("locNames") or []
        location = " / ".join(str(value) for value in locations if value)
        location = location or "Unknown"
        category = classify_official_location(location)
        if category == LocationCategory.EXCLUDED:
            continue
        description = "\n\n".join(
            str(value).strip()
            for value in (item.get("Duty"), item.get("Require"))
            if value
        )
        source_url = (
            f"{portal_root}/social/detail?jobAdId={source_job_id}"
        )
        posted_at = item.get("PostDate")
        if not posted_at or str(posted_at).startswith("0001-"):
            posted_at = item.get("ChangeDate")
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
                "posted_at": posted_at,
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
