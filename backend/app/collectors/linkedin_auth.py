import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from app.collectors.authenticated_playwright import AuthenticatedPlaywrightCollector
from app.collectors.base import CollectorMeta


class LinkedInAuthCollector(AuthenticatedPlaywrightCollector):
    meta = CollectorMeta(
        source_name="linkedin_auth",
        source_type="job_platform",
        collection_method="browser_automation",
        polling_interval_minutes=20,
        search_configuration="env:LINKEDIN_SEARCH_URLS",
        parser_name="linkedin-search-result-parser",
        normalization_logic="app.normalization.normalizer.normalize_job",
    )
    base_domain = "linkedin.com"

    def is_enabled(self) -> bool:
        return self.settings.linkedin_auth_enabled

    def get_search_urls(self) -> List[str]:
        return self.settings.csv_items(self.settings.linkedin_search_urls)

    def get_storage_state_path(self) -> Optional[str]:
        return self.settings.linkedin_auth_storage_state_path

    def perform_login(self, page: Any) -> None:
        if not self.settings.linkedin_auth_username or not self.settings.linkedin_auth_password:
            return
        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=45000)
        page.fill("#username", self.settings.linkedin_auth_username)
        page.fill("#password", self.settings.linkedin_auth_password)
        page.click("button[type='submit']")
        page.wait_for_timeout(3000)

    def is_job_url(self, url: str) -> bool:
        lowered = url.lower()
        return "linkedin.com/jobs/view/" in lowered

    def fetch_raw(self) -> List[Dict[str, Any]]:
        if not self.is_enabled():
            return []
        search_urls = self.get_search_urls()
        if not search_urls:
            return []

        from playwright.sync_api import sync_playwright

        results: Dict[str, Dict[str, Any]] = {}
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--ignore-certificate-errors"])
            context_args: Dict[str, Any] = {"ignore_https_errors": True}
            state_path = self.get_storage_state_path()
            if state_path:
                context_args["storage_state"] = state_path
            context = browser.new_context(**context_args)
            page = context.new_page()

            if not state_path:
                self.perform_login(page)

            for search_url in search_urls:
                try:
                    fallback_location = self._expected_location_from_search_url(search_url)
                    page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(3500)
                    cards = self._extract_linkedin_cards(page)
                    for card in cards[:25]:
                        detail = self._collect_detail(context, card["job_url"])
                        merged = self._merge_job_data(card, detail, fallback_location=fallback_location)
                        source_job_id = merged["source_job_id"]
                        results[source_job_id] = merged
                except Exception:
                    continue

            context.close()
            browser.close()

        return list(results.values())

    def _extract_linkedin_cards(self, page: Any) -> List[Dict[str, str]]:
        payload = page.evaluate(
            """
            () => {
              const items = [];
              const cards = Array.from(document.querySelectorAll("li.jobs-search-results__list-item, li.scaffold-layout__list-item"));
              for (const card of cards) {
                const link = card.querySelector("a.job-card-list__title--link, a.job-card-container__link, a[href*='/jobs/view/']");
                if (!link || !link.href) continue;
                const titleEl = card.querySelector("a.job-card-list__title--link strong, a.job-card-list__title--link span, h3, .job-card-list__title");
                const companyEl = card.querySelector(".job-card-container__company-name, .job-card-list__subtitle, .artdeco-entity-lockup__subtitle span");
                const locationEl = card.querySelector(".job-card-container__metadata-item, .job-card-container__metadata-wrapper li, .job-card-container__metadata-item--workplace-type");
                items.push({
                  job_url: link.href,
                  title: titleEl?.textContent?.trim() || link.textContent?.trim() || "",
                  company: companyEl?.textContent?.trim() || "",
                  location: locationEl?.textContent?.trim() || ""
                });
              }
              return items;
            }
            """
        )
        cards: List[Dict[str, str]] = []
        for item in payload:
            title = self.clean_text(item.get("title", ""))
            job_url = self._clean_linkedin_job_url(item.get("job_url", ""))
            if not title or not job_url:
                continue
            if "/jobs/view/" not in job_url:
                continue
            cards.append(
                {
                    "title": title[:255],
                    "company": self.clean_text(item.get("company", ""))[:255],
                    "location": self.clean_text(item.get("location", ""))[:255],
                    "job_url": job_url,
                }
            )
        return cards

    def _collect_detail(self, context: Any, job_url: str) -> Dict[str, str]:
        page = context.new_page()
        try:
            page.goto(job_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2500)
            html = page.content()
            payload = page.evaluate(
                """
                () => {
                  const text = (sel) => {
                    const node = document.querySelector(sel);
                    return node?.textContent?.trim() || "";
                  };
                  const descNode = document.querySelector(
                    ".show-more-less-html__markup, .jobs-description-content__text, div.jobs-box__html-content, .jobs-description__content"
                  );
                  return {
                    title:
                      text(".job-details-jobs-unified-top-card__job-title") ||
                      text(".top-card-layout__title") ||
                      text("h1"),
                    company:
                      text(".job-details-jobs-unified-top-card__company-name a") ||
                      text(".job-details-jobs-unified-top-card__company-name") ||
                      text(".topcard__org-name-link") ||
                      text(".topcard__flavor-row a"),
                    location:
                      text(".job-details-jobs-unified-top-card__bullet") ||
                      text(".topcard__flavor--bullet") ||
                      text(".job-details-jobs-unified-top-card__tertiary-description-container"),
                    description:
                      descNode?.textContent?.trim() || ""
                  };
                }
                """
            )
            ld_payload = self._extract_ld_job_fields(html)
            title = self.clean_text(payload.get("title", ""))[:255] or ld_payload.get("title", "")
            company = self.clean_text(payload.get("company", ""))[:255] or ld_payload.get("company", "")
            location = self.clean_text(payload.get("location", ""))[:255] or ld_payload.get("location", "")
            description = self.clean_text(payload.get("description", ""))[:5000] or ld_payload.get("description", "")
            return {
                "title": title,
                "company": company,
                "location": self._normalize_location(location),
                "description": description,
            }
        except Exception:
            return {"title": "", "company": "", "location": "", "description": ""}
        finally:
            page.close()

    def _merge_job_data(self, card: Dict[str, str], detail: Dict[str, str], fallback_location: str) -> Dict[str, str]:
        title = detail["title"] or card["title"]
        company = detail["company"] or card["company"] or "Unknown Company"
        location = detail["location"] or card["location"] or fallback_location or "Unknown"
        location = self._normalize_location(location)
        description = self._clean_description(detail["description"]) or f"{title} at {company} in {location}"
        job_url = card["job_url"]
        source_job_id = self.extract_source_job_id(job_url, title, company, location)
        return {
            "source_job_id": source_job_id,
            "title": title[:255],
            "company": company[:255],
            "location": location[:255],
            "country": self.derive_country(location),
            "description": description[:5000],
            "apply_url": job_url,
            "source_url": job_url,
            "content_hash": self.build_hash(source_job_id, title, company, location, description),
        }

    def _clean_linkedin_job_url(self, raw_url: str) -> str:
        if not raw_url:
            return ""
        parsed = urlparse(raw_url)
        clean = parsed
        if not parsed.netloc:
            clean = urlparse(urljoin("https://www.linkedin.com", raw_url))
        path_match = re.search(r"/jobs/view/(\\d+)", clean.path)
        if path_match:
            canonical_path = f"/jobs/view/{path_match.group(1)}/"
            return urlunparse((clean.scheme or "https", clean.netloc or "www.linkedin.com", canonical_path, "", "", ""))
        return urlunparse((clean.scheme or "https", clean.netloc or "www.linkedin.com", clean.path, "", "", ""))

    def _clean_description(self, text: str) -> str:
        cleaned = self.clean_text(text)
        if not cleaned:
            return ""
        lowered = cleaned.lower()
        noise_markers = [
            "skip to main content",
            "join now",
            "sign in",
            "cookies",
            "privacy policy",
            "user agreement",
            "跳到主要内容",
            "登录",
            "立即加入",
            "cookie",
        ]
        if any(marker in lowered for marker in noise_markers):
            return ""
        if len(cleaned) > 3500:
            cleaned = cleaned[:3500]
        return cleaned

    def _extract_ld_job_fields(self, html: str) -> Dict[str, str]:
        soup = BeautifulSoup(html, "html.parser")
        scripts = soup.select("script[type='application/ld+json']")
        for script in scripts:
            raw = script.string or script.get_text()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except Exception:
                continue
            objects = data if isinstance(data, list) else [data]
            for item in objects:
                if not isinstance(item, dict):
                    continue
                obj_type = str(item.get("@type", "")).lower()
                if "jobposting" not in obj_type:
                    continue
                company = ""
                hiring_org = item.get("hiringOrganization")
                if isinstance(hiring_org, dict):
                    company = str(hiring_org.get("name", "")).strip()
                location = ""
                job_location = item.get("jobLocation")
                if isinstance(job_location, dict):
                    address = job_location.get("address")
                    if isinstance(address, dict):
                        locality = str(address.get("addressLocality", "")).strip()
                        region = str(address.get("addressRegion", "")).strip()
                        country = str(address.get("addressCountry", "")).strip()
                        location = " ".join(part for part in [locality, region, country] if part).strip()
                description = self.clean_text(str(item.get("description", "")))
                title = str(item.get("title", "")).strip()
                return {
                    "title": title[:255],
                    "company": company[:255],
                    "location": self._normalize_location(location)[:255],
                    "description": description[:5000],
                }
        return {"title": "", "company": "", "location": "", "description": ""}

    def _expected_location_from_search_url(self, search_url: str) -> str:
        parsed = urlparse(search_url)
        query = parse_qs(parsed.query)
        for key in ("location", "geoId"):
            values = query.get(key, [])
            if values:
                if key == "location":
                    return self._normalize_location(values[0])
                if key == "geoId":
                    geo_map = {
                        "102454443": "Singapore",
                        "104305776": "Hong Kong",
                        "102890883": "Shanghai",
                    }
                    mapped = geo_map.get(values[0])
                    if mapped:
                        return mapped
        return "Unknown"

    def _normalize_location(self, location: str) -> str:
        text = self.clean_text(location)
        if "·" in text:
            text = text.split("·")[0].strip()
        if "|" in text:
            text = text.split("|")[0].strip()
        # Common LinkedIn format: "Singapore, Singapore"
        if "," in text:
            head = text.split(",")[0].strip()
            if head:
                return head
        return text
