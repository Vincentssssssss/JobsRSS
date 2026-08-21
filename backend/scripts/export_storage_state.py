#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


SITE_DOMAINS = {
    "linkedin": ("linkedin.com",),
    "liepin": ("liepin.com",),
    "job51": ("51job.com",),
}


def domain_matches(host: str, allowed_domains: tuple[str, ...]) -> bool:
    normalized = host.lower().lstrip(".").rstrip(".")
    return any(
        normalized == allowed or normalized.endswith(f".{allowed}")
        for allowed in allowed_domains
    )


def filter_storage_state(state: dict, allowed_domains: tuple[str, ...]) -> dict:
    cookies = [
        cookie
        for cookie in state.get("cookies", [])
        if domain_matches(cookie.get("domain", ""), allowed_domains)
    ]
    origins = []
    for origin in state.get("origins", []):
        host = urlparse(origin.get("origin", "")).hostname or ""
        if domain_matches(host, allowed_domains):
            origins.append(origin)
    return {"cookies": cookies, "origins": origins}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export a site-scoped Playwright storage state from an existing Chrome CDP session."
    )
    parser.add_argument("--site", required=True, choices=sorted(SITE_DOMAINS))
    parser.add_argument("--out", required=True)
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    args = parser.parse_args()

    output = Path(args.out).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(args.cdp_url)
        if not browser.contexts:
            raise SystemExit("No Chrome browser context found on the CDP endpoint.")
        context = browser.contexts[0]
        filtered = filter_storage_state(context.storage_state(), SITE_DOMAINS[args.site])

    if not filtered["cookies"]:
        raise SystemExit(
            f"No {args.site} cookies found. Log in to {args.site} in the CDP Chrome window and retry."
        )

    output.write_text(json.dumps(filtered, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(output, 0o600)
    print(f"saved {len(filtered['cookies'])} cookies to {output}")


if __name__ == "__main__":
    main()
