import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from app.collectors.authenticated_playwright import AuthenticatedPlaywrightCollector
from app.collectors.base import CollectorMeta
from app.enrichment.external_job import (
    ExternalJobEnricher,
    EnrichedJobData,
    merge_job_fields,
)

_DESCRIPTION_NOISE_MARKERS = {
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
}
_DESCRIPTION_ROLE_SIGNALS = {
    "responsibilities",
    "responsibility",
    "requirements",
    "requirement",
    "qualifications",
    "qualification",
    "what you'll do",
    "what you will do",
    "what we're looking for",
    "about the role",
    "security",
    "network",
    "platform",
    "cloud",
    "waf",
    "ddos",
    "firewall",
    "ids",
    "ips",
    "iam",
    "soc",
    "siem",
    "岗位职责",
    "任职要求",
    "职位要求",
    "任职资格",
    "职责",
    "要求",
    "资格",
    "安全",
    "网络",
    "云",
}
_DESCRIPTION_INTRO_MARKERS = {
    "founded in",
    "who are we",
    "what do we do",
    "about us",
    "about the company",
    "our mission",
    "our values",
    "our team",
    "economic and social value",
    "membership club",
}
_DESCRIPTION_SPLIT_MARKERS = [
    "Who are we?",
    "What do we do?",
    "Responsibilities",
    "Responsibility",
    "Requirements",
    "Requirement",
    "Qualifications",
    "Qualification",
    "What you'll do",
    "What you will do",
    "About the role",
    "岗位职责",
    "任职要求",
    "职位要求",
    "任职资格",
]


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

    def __init__(self) -> None:
        super().__init__()
        self.external_enricher = ExternalJobEnricher(
            timeout_seconds=self.settings.linkedin_external_enrichment_timeout_seconds
        )

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
                        if not self._passes_strict_location_filter(
                            merged,
                            self.settings.csv_items(
                                self.settings.linkedin_allowed_locations
                            ),
                        ):
                            continue
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
              const links = Array.from(document.querySelectorAll("a[href*='/jobs/view/']"));
              for (const link of links) {
                if (!link.href) continue;
                const card =
                  link.closest("[data-job-id], li, article, .job-card-container, .artdeco-entity-lockup") ||
                  link.parentElement;
                if (!card) continue;
                const titleEl = card.querySelector("a.job-card-list__title--link strong, a.job-card-list__title--link span, h3, .job-card-list__title");
                const companyEl = card.querySelector(
                  ".job-card-container__company-name, .job-card-list__subtitle, " +
                  ".artdeco-entity-lockup__subtitle span, .artdeco-entity-lockup__subtitle, " +
                  "[data-test-job-card-company-name]"
                );
                const locationEl = card.querySelector(
                  ".job-card-container__metadata-item, .job-card-container__metadata-wrapper li, " +
                  ".job-card-container__metadata-item--workplace-type, " +
                  ".artdeco-entity-lockup__caption, [data-test-job-card-location]"
                );
                const timeEl = card.querySelector("time, .job-search-card__listdate");
                items.push({
                  job_url: link.href,
                  title:
                    titleEl?.textContent?.trim() ||
                    link.getAttribute("aria-label")?.trim() ||
                    link.textContent?.trim() ||
                    "",
                  company: companyEl?.textContent?.trim() || "",
                  location: locationEl?.textContent?.trim() || "",
                  listed_at_text: timeEl?.textContent?.trim() || "",
                  listed_at_datetime: timeEl?.getAttribute("datetime") || ""
                });
              }
              return items;
            }
            """
        )
        cards: List[Dict[str, str]] = []
        seen_urls = set()
        for item in payload:
            original_job_url = item.get("job_url", "")
            job_url = self._clean_linkedin_job_url(original_job_url)
            title = self.clean_text(item.get("title", "")) or self._title_from_job_url(original_job_url)
            if not title or not job_url:
                continue
            if "/jobs/view/" not in job_url:
                continue
            if job_url in seen_urls:
                continue
            seen_urls.add(job_url)
            posted_at = item.get("listed_at_datetime") or self.extract_posted_at(item.get("listed_at_text", ""))
            cards.append(
                {
                    "title": title[:255],
                    "company": (
                        self.clean_text(item.get("company", ""))
                        or self._company_from_job_url(original_job_url)
                    )[:255],
                    "location": self.clean_text(item.get("location", ""))[:255],
                    "job_url": job_url,
                    "posted_at": posted_at,
                }
            )
        return cards

    def _collect_detail(self, context: Any, job_url: str) -> Dict[str, Any]:
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
            description = (payload.get("description", "") or ld_payload.get("description", ""))[:8000]
            external_apply_url = self._discover_external_apply_url(page)
            official = self._collect_official_job(external_apply_url)
            return {
                "title": title,
                "company": company,
                "location": self._normalize_location(location),
                "description": description,
                "external_apply_url": external_apply_url,
                "official": official,
            }
        except Exception:
            return {
                "title": "",
                "company": "",
                "location": "",
                "description": "",
                "external_apply_url": "",
                "official": None,
            }
        finally:
            page.close()

    def _merge_job_data(self, card: Dict[str, str], detail: Dict[str, Any], fallback_location: str) -> Dict[str, Any]:
        title = detail["title"] or card["title"]
        job_url = card["job_url"]
        company = (
            detail["company"]
            or card["company"]
            or self._company_from_job_url(job_url)
            or "Unknown Company"
        )
        location, location_source = self._resolve_location(
            detail_location=detail["location"],
            card_location=card["location"],
            fallback_location=fallback_location,
        )
        description = self._clean_description(detail["description"]) or f"{title} at {company} in {location}"
        base = {
            "title": title,
            "company": company,
            "location": location,
            "description": description,
            "job_url": job_url,
            "source_url": job_url,
            "apply_url": detail.get("external_apply_url") or job_url,
            "posted_at": card.get("posted_at"),
        }
        enriched = merge_job_fields(base, detail.get("official"))
        title = enriched["title"]
        company = enriched["company"]
        enriched_location = self._normalize_location(enriched["location"])
        if enriched_location:
            location = enriched_location
            if detail.get("official") is not None:
                location_source = "official"
        description = self._clean_description(enriched["description"]) or f"{title} at {company} in {location}"
        source_job_id = self.extract_source_job_id(job_url, title, company, location)
        return {
            "source_job_id": source_job_id,
            "title": title[:255],
            "company": company[:255],
            "location": location[:255],
            "country": self.derive_country(location),
            "description": description[:5000],
            "apply_url": enriched["apply_url"],
            "source_url": job_url,
            "posted_at": enriched.get("posted_at"),
            "location_source": location_source,
            "enrichment_source": (
                detail["official"].provider if detail.get("official") else None
            ),
            "content_hash": self.build_hash(
                source_job_id,
                title,
                company,
                location,
                description,
                enriched["apply_url"],
                enriched.get("posted_at").isoformat()
                if hasattr(enriched.get("posted_at"), "isoformat")
                else str(enriched.get("posted_at") or ""),
            ),
        }

    def _clean_linkedin_job_url(self, raw_url: str) -> str:
        if not raw_url:
            return ""
        parsed = urlparse(raw_url)
        clean = parsed
        if not parsed.netloc:
            clean = urlparse(urljoin("https://www.linkedin.com", raw_url))
        path_match = re.search(r"/jobs/view/(?:.*-)?(\d+)/?$", clean.path)
        if path_match:
            canonical_path = f"/jobs/view/{path_match.group(1)}/"
            return urlunparse((clean.scheme or "https", clean.netloc or "www.linkedin.com", canonical_path, "", "", ""))
        return urlunparse((clean.scheme or "https", clean.netloc or "www.linkedin.com", clean.path, "", "", ""))

    def _company_from_job_url(self, job_url: str) -> str:
        slug = urlparse(job_url).path.rstrip("/").split("/")[-1]
        match = re.search(r"-at-(.+?)-\d+$", slug)
        if not match:
            return ""
        words = [word for word in match.group(1).split("-") if word]
        return " ".join(word.upper() if word in {"aws", "ibm", "dbs", "sap"} else word.title() for word in words)

    def _title_from_job_url(self, job_url: str) -> str:
        slug = urlparse(job_url).path.rstrip("/").split("/")[-1]
        slug = re.sub(r"-\d+$", "", slug)
        if "-at-" in slug:
            slug = slug.split("-at-", 1)[0]
        words = [word for word in slug.split("-") if word]
        special = {"ai": "AI", "iam": "IAM", "aws": "AWS", "api": "API", "devsecops": "DevSecOps"}
        return " ".join(special.get(word, word.title()) for word in words)

    def _discover_external_apply_url(self, page: Any) -> str:
        candidates = page.evaluate(
            """
            () => Array.from(document.querySelectorAll("a[href]"))
              .filter((link) => {
                const text = (link.textContent || "").trim().toLowerCase();
                const klass = String(link.className || "").toLowerCase();
                return text === "apply" || text.includes("apply on company") || klass.includes("apply-button");
              })
              .map((link) => link.href)
            """
        )
        for candidate in candidates:
            if self._is_external_apply_url(candidate):
                return candidate
        return ""

    def _is_external_apply_url(self, url: str) -> bool:
        if not ExternalJobEnricher.is_safe_public_url(url):
            return False
        host = (urlparse(url).hostname or "").lower()
        return not (host == "linkedin.com" or host.endswith(".linkedin.com"))

    def _collect_official_job(self, official_url: str) -> Optional[EnrichedJobData]:
        if not self.settings.linkedin_external_enrichment_enabled or not official_url:
            return None
        if not ExternalJobEnricher.is_supported_ats_url(official_url, resolve_dns=True):
            return None
        enriched = self.external_enricher.enrich(official_url)
        return enriched if enriched and enriched.has_authoritative_content else None

    def _clean_description(self, text: str) -> str:
        prepared = self._prepare_description_text(text)
        if not prepared:
            return ""
        lines = [self.clean_text(line) for line in prepared.split("\n")]
        lines = [line for line in lines if line]
        if not lines:
            return ""
        filtered = [line for line in lines if not self._is_noise_line(line)]
        if not filtered:
            filtered = lines
        curated = self._curate_role_lines(filtered)
        cleaned = "\n".join(curated if curated else filtered)
        if len(cleaned) > 3500:
            cleaned = cleaned[:3500]
        return cleaned

    def _prepare_description_text(self, text: str) -> str:
        raw = (text or "").strip()
        if not raw:
            return ""
        if "<" in raw and ">" in raw:
            raw = BeautifulSoup(raw, "html.parser").get_text("\n", strip=True)
        normalized = raw.replace("\r\n", "\n").replace("\r", "\n").replace("\u200b", "")
        if "\n" not in normalized:
            for marker in _DESCRIPTION_SPLIT_MARKERS:
                normalized = re.sub(
                    rf"\s*({re.escape(marker)})\s*",
                    r"\n\1 ",
                    normalized,
                    flags=re.IGNORECASE,
                )
        return normalized.strip()

    def _is_noise_line(self, line: str) -> bool:
        lowered = line.lower()
        return any(marker in lowered for marker in _DESCRIPTION_NOISE_MARKERS)

    def _has_role_signal(self, line: str) -> bool:
        lowered = line.lower()
        return any(marker in lowered for marker in _DESCRIPTION_ROLE_SIGNALS)

    def _is_intro_line(self, line: str) -> bool:
        lowered = line.lower()
        return any(marker in lowered for marker in _DESCRIPTION_INTRO_MARKERS)

    def _curate_role_lines(self, lines: List[str]) -> List[str]:
        if not lines:
            return []
        first_signal = next(
            (index for index, line in enumerate(lines) if self._has_role_signal(line)),
            None,
        )
        working_lines = lines[first_signal:] if first_signal is not None else lines

        curated: List[str] = []
        keep_next = 0
        for line in working_lines:
            has_role_signal = self._has_role_signal(line)
            if self._is_intro_line(line) and not has_role_signal:
                continue
            if has_role_signal:
                curated.append(line)
                keep_next = 2
                continue
            if keep_next > 0:
                curated.append(line)
                keep_next -= 1
                continue
            if re.match(r"^\s*(?:[-*•●·▪◦]|\d+[.)]|[a-zA-Z][.)])\s*", line):
                curated.append(line)
        return curated

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

    def _resolve_location(
        self,
        *,
        detail_location: str,
        card_location: str,
        fallback_location: str,
    ) -> tuple[str, str]:
        normalized_detail = self._normalize_location(detail_location)
        if normalized_detail:
            return normalized_detail, "detail"
        normalized_card = self._normalize_location(card_location)
        if normalized_card:
            return normalized_card, "card"
        normalized_fallback = self._normalize_location(fallback_location)
        if normalized_fallback and normalized_fallback.lower() != "unknown":
            return normalized_fallback, "fallback"
        return "Unknown", "unknown"

    def _passes_strict_location_filter(
        self,
        merged: Dict[str, Any],
        allowed_locations: List[str],
    ) -> bool:
        if not self.settings.linkedin_strict_location_filter:
            return True
        if merged.get("location_source") == "fallback":
            return False
        return self._is_allowed_location(merged.get("location", ""), allowed_locations)

    def _is_allowed_location(self, location: str, allowed_locations: List[str]) -> bool:
        normalized = self.clean_text(location).lower()
        if not normalized or normalized == "unknown":
            return False
        aliases = {
            "singapore": {"singapore", "新加坡"},
            "hong kong": {"hong kong", "香港"},
            "shanghai": {"shanghai", "上海"},
            "hangzhou": {"hangzhou", "杭州"},
        }
        for allowed in allowed_locations:
            key = self.clean_text(allowed).lower()
            candidates = aliases.get(key, {key})
            if any(candidate in normalized for candidate in candidates):
                return True
        return False
