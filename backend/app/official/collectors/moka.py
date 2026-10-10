import base64
import json
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.core.config import get_settings
from app.official.collectors.base import OfficialCollectorBase
from app.official.location import LocationCategory, classify_official_location
from app.official.registry import get_official_source

MOKA_API_ROOT = "https://app.mokahr.com"


class MokaOfficialCollector(OfficialCollectorBase):
    def __init__(
        self,
        source_id: str,
        company: str,
        portal_url: str,
        org_id: str,
        site_id: str,
        location_ids: Optional[List[int]] = None,
        detail_route: str = "/#/job/{id}",
    ) -> None:
        super().__init__(
            get_official_source(source_id),
            method="encrypted_json",
            parser_name="moka-aes-json",
        )
        self.company = company
        self.portal_url = portal_url
        self.org_id = org_id
        self.site_id = site_id
        self.location_ids = location_ids
        self.detail_route = detail_route

    def fetch_raw(self) -> List[Dict[str, Any]]:
        settings = get_settings()
        jobs: List[Dict[str, Any]] = []
        with httpx.Client(
            timeout=settings.official_source_timeout_seconds,
            verify=settings.official_source_verify_tls,
            follow_redirects=False,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json,*/*",
                "Origin": MOKA_API_ROOT,
                "Referer": self.portal_url,
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        ) as client:
            iv = self._bootstrap(client)
            offset = 0
            page_size = 50
            total = None
            page_count = 0
            while (
                (total is None or offset < total)
                and page_count < settings.official_source_max_pages_per_source
            ):
                page_count += 1
                body: Dict[str, Any] = {
                    "orgId": self.org_id,
                    "siteId": self.site_id,
                    "site": "social",
                    "limit": page_size,
                    "offset": offset,
                    "needStat": True,
                    "locale": "zh-CN",
                }
                if self.location_ids:
                    body["locationIds"] = self.location_ids
                decoded = self._post_decrypted(
                    client,
                    (
                        f"{MOKA_API_ROOT}/api/outer/ats-apply/"
                        f"website/jobs/v2?orgId={self.org_id}"
                    ),
                    body,
                    iv,
                )
                data = decoded.get("data") or {}
                rows = data.get("jobs") or []
                total = int(
                    (data.get("jobStats") or {}).get("total") or len(rows)
                )
                if not rows:
                    break
                for row in rows:
                    location = _moka_location(row)
                    category = classify_official_location(location)
                    if category == LocationCategory.EXCLUDED:
                        continue
                    detail = self._post_decrypted(
                        client,
                        (
                            f"{MOKA_API_ROOT}/api/outer/ats-apply/"
                            f"website/job?orgId={self.org_id}"
                        ),
                        {
                            "orgId": self.org_id,
                            "siteId": self.site_id,
                            "jobId": row.get("id"),
                            "locale": "zh-CN",
                        },
                        iv,
                    )
                    detail_job = (detail.get("data") or {}).get("job") or (
                        detail.get("data") or {}
                    )
                    job = parse_moka_job(
                        detail_job,
                        company=self.company,
                        source_root=self.portal_url,
                        detail_route=self.detail_route,
                    )
                    if job is not None:
                        jobs.append(job)
                    if len(jobs) >= settings.official_source_max_jobs_per_source:
                        return jobs
                offset += len(rows)
        return jobs

    def _bootstrap(self, client: httpx.Client) -> str:
        response = _same_host_get(client, self.portal_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        node = soup.select_one("#init-data")
        if not node or not node.get("value"):
            raise RuntimeError("Moka portal init-data was not found")
        init = json.loads(str(node.get("value")))
        iv = str(init.get("aesIv") or "")
        if len(iv.encode("utf-8")) != 16:
            raise RuntimeError("Moka portal returned an invalid AES IV")
        return iv

    def _post_decrypted(
        self,
        client: httpx.Client,
        url: str,
        body: Dict[str, Any],
        iv: str,
    ) -> Dict[str, Any]:
        response = client.post(url, json=body)
        response.raise_for_status()
        decoded = decrypt_moka_response(response.json(), iv)
        if decoded.get("code") != 0:
            raise RuntimeError(f"Moka API returned code {decoded.get('code')}")
        return decoded


class GskOfficialCollector(MokaOfficialCollector):
    def __init__(self) -> None:
        super().__init__(
            source_id="gsk",
            company="GSK",
            portal_url=(
                "https://app.mokahr.com/social-recruitment/gsk/148067"
            ),
            org_id="gsk",
            site_id="148067",
            location_ids=[579170, 599254],
        )


class WuXiBiologicsOfficialCollector(MokaOfficialCollector):
    def __init__(self) -> None:
        super().__init__(
            source_id="wuxi_biologics",
            company="WuXi Biologics / 药明生物",
            portal_url=(
                "https://job.wuxibiologics.com.cn/"
                "social-recruitment/wuxibiologics/99960"
            ),
            org_id="wuxibiologics",
            site_id="99960",
            detail_route="/#/jobs/{id}",
        )


class AntaOfficialCollector(MokaOfficialCollector):
    def __init__(self) -> None:
        super().__init__(
            source_id="anta",
            company="ANTA Group / 安踏集团",
            portal_url="https://jobs.anta.com/social-recruitment/antahr/146041/",
            org_id="antahr",
            site_id="146041",
        )


class KpmgOfficialCollector(MokaOfficialCollector):
    def __init__(self) -> None:
        super().__init__(
            source_id="kpmg",
            company="KPMG / 毕马威",
            portal_url="https://app.mokahr.com/social-recruitment/kpmg/68240",
            org_id="kpmg",
            site_id="68240",
        )


def decrypt_moka_response(payload: Dict[str, Any], iv: str) -> Dict[str, Any]:
    key = str(payload.get("necromancer") or "").encode("utf-8")
    iv_bytes = iv.encode("utf-8")
    if len(key) != 16 or len(iv_bytes) != 16:
        raise ValueError("Moka AES key and IV must both be 16 bytes")
    ciphertext = base64.b64decode(str(payload.get("data") or ""))
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv_bytes)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    plaintext = unpadder.update(padded) + unpadder.finalize()
    return json.loads(plaintext.decode("utf-8"))


def parse_moka_job(
    item: Dict[str, Any],
    company: str,
    source_root: str,
    detail_route: str = "/#/job/{id}",
) -> Dict[str, Any] | None:
    source_job_id = str(item.get("id") or "").strip()
    title = str(item.get("title") or "").strip()
    if not source_job_id or not title:
        return None
    location = _moka_location(item)
    category = classify_official_location(location)
    if category == LocationCategory.EXCLUDED:
        return None
    description = BeautifulSoup(
        str(item.get("jobDescription") or item.get("description") or ""),
        "html.parser",
    ).get_text("\n", strip=True)
    source_url = f"{source_root.rstrip('/')}{detail_route.format(id=source_job_id)}"
    return {
        "source_job_id": source_job_id,
        "company": company,
        "title": title,
        "location": location,
        "country": "China",
        "description": description,
        "apply_url": source_url,
        "source_url": source_url,
        "posted_at": item.get("publishedAt") or item.get("openedAt"),
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


def _moka_location(item: Dict[str, Any]) -> str:
    locations = item.get("locations") or []
    rendered = []
    for location in locations:
        if not isinstance(location, dict):
            rendered.append(str(location))
            continue
        parts = [
            location.get("cityName"),
            _city_name_from_moka_city_id(location.get("cityId")),
            location.get("provinceName"),
            location.get("country"),
            location.get("address"),
        ]
        text = ", ".join(str(part) for part in parts if part)
        if text:
            rendered.append(text)
    return " / ".join(dict.fromkeys(rendered)) or "Unknown"


def _city_name_from_moka_city_id(city_id: Any) -> str:
    text = str(city_id or "").strip()
    if text.startswith("310"):
        return "上海"
    return ""


def _same_host_get(
    client: httpx.Client, url: str, max_redirects: int = 3
) -> httpx.Response:
    original_host = (urlparse(url).hostname or "").lower()
    current = url
    response: httpx.Response | None = None
    for _ in range(max_redirects + 1):
        response = client.get(current, follow_redirects=False)
        if not response.is_redirect:
            return response
        location = response.headers.get("location")
        if not location:
            return response
        target = urljoin(current, location)
        parsed = urlparse(target)
        if parsed.scheme != "https" or (parsed.hostname or "").lower() != original_host:
            raise RuntimeError("Moka portal redirected outside its official host")
        current = target
    assert response is not None
    return response
