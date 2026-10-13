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
SITE_LOGIN_URLS = {
    "linkedin": "https://www.linkedin.com/login",
    "liepin": "https://www.liepin.com/",
    "job51": "https://www.51job.com/",
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


def export_state_from_cdp(site: str, cdp_url: str) -> dict:
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
        if not browser.contexts:
            raise SystemExit("No Chrome browser context found on the CDP endpoint.")
        context = browser.contexts[0]
        return filter_storage_state(context.storage_state(), SITE_DOMAINS[site])


def export_state_interactive(site: str, browser_channel: str, user_data_dir: str) -> dict:
    profile_dir = Path(user_data_dir).expanduser().resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)
    login_url = SITE_LOGIN_URLS[site]
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            channel=browser_channel,
            headless=False,
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
        print(
            f"Please complete login in the opened browser for site={site}. "
            "Press Enter here after login succeeds."
        )
        input()
        state = context.storage_state()
        context.close()
    return filter_storage_state(state, SITE_DOMAINS[site])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export a site-scoped Playwright storage state from an existing Chrome CDP session."
    )
    parser.add_argument("--site", required=True, choices=sorted(SITE_DOMAINS))
    parser.add_argument("--out", required=True)
    parser.add_argument("--mode", choices=["cdp", "interactive"], default="cdp")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    parser.add_argument("--browser-channel", default="chrome")
    parser.add_argument(
        "--user-data-dir",
        default="~/.jobsrss-playwright-profile",
        help="Used only for --mode interactive",
    )
    args = parser.parse_args()

    output = Path(args.out).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    if args.mode == "interactive":
        filtered = export_state_interactive(
            site=args.site,
            browser_channel=args.browser_channel,
            user_data_dir=args.user_data_dir,
        )
    else:
        try:
            filtered = export_state_from_cdp(site=args.site, cdp_url=args.cdp_url)
        except Exception as exc:
            message = str(exc)
            if "Browser context management is not supported" in message:
                raise SystemExit(
                    "CDP export failed: browser does not support context management. "
                    "Retry with: --mode interactive"
                ) from exc
            raise

    if not filtered["cookies"]:
        raise SystemExit(
            f"No {args.site} cookies found. Log in to {args.site} in the CDP Chrome window and retry."
        )

    output.write_text(json.dumps(filtered, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(output, 0o600)
    print(f"saved {len(filtered['cookies'])} cookies to {output}")


if __name__ == "__main__":
    main()
