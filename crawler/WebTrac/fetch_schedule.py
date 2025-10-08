#!/usr/bin/env python3
"""
webtrac_schedule.py

Fetch daily tennis-court schedules from WebTrac-powered sites:
- Finds available vs unavailable time slots for each court
- Supports multiple cities: Burlingame, San Mateo, Albany
- Uses config-based parameters for different WebTrac instances

Usage examples:
  python fetch_schedule.py --date 2025-10-06 --query_mode burlingame
  python fetch_schedule.py --date 2025-10-06 --query_mode san_mateo
  python fetch_schedule.py --date 2025-10-06 --query_mode albany

Notes:
- Be gentle: WebTrac is a shared parks system. Keep request rates low.
- This scrapes public info shown on the results & item pages.
- City-specific parameters are configured in config_webtrac.json.
"""

import argparse
import json
import os
import re
import time
from datetime import datetime
from urllib.parse import urlencode
from typing import Dict, List, Tuple, Optional

import requests
from bs4 import BeautifulSoup, NavigableString
try:
    from parse_webtrac_listing import (
        parse_listing_table_schedules,
        parse_listing_group_schedules,
    )
except ImportError:
    # Fallback when executed as a module from project root
    from crawler.parse_webtrac_listing import (
        parse_listing_table_schedules,
        parse_listing_group_schedules,
    )

BASE = "https://caburlingameweb.myvscloud.com"  # default; can be overridden via CLI
SEARCH_PATH = "/webtrac/web/search.html"
ITEMINFO_PATH = "/webtrac/web/iteminfo.html"

BROWSER_HEADERS = {
    # modern but generic; keep your contact on user-agent tail
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/123.0 Safari/537.36 CourtFinder/0.1 (+contact@example.com)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    # These aren't required, but some CDNs look at them
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    # Client hints often checked by WAF
    "Sec-CH-UA": '"Chromium";v="123", "Not:A-Brand";v="8"',
    "Sec-CH-UA-Platform": '"macOS"',
    "Sec-CH-UA-Mobile": "?0",
}

TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\s*(?:am|pm)\s*-\s*\d{1,2}:\d{2}\s*(?:am|pm)\b", re.I)

def get_csrf_token(sess: requests.Session) -> str:
    """
    Load the Facility Search start page to get a fresh CSRF token.
    """
    url = f"{BASE}{SEARCH_PATH}"
    # Minimal query to land on Facility Rentals search with form present.
    params = {"Action": "Start", "module": "FR"}
    r = sess.get(url, params=params, headers=BROWSER_HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    token_input = soup.find("input", {"name": "_csrf_token"})
    if not token_input or not token_input.get("value"):
        # Some tenants echo a token in a meta tag or script; try a fallback
        meta = soup.find("meta", {"name": "_csrf_token"})
        if meta and meta.get("content"):
            return meta["content"]
        raise RuntimeError("Could not find CSRF token on start page")
    return token_input["value"]

def bootstrap_and_get_token(sess: requests.Session, base_url: str = BASE, max_retries: int = 2) -> str:
    """
    Start at the tenant's home page to get cookies, then load the FR Start page to grab CSRF.
    Retries once if a 403 occurs (common WAF behavior).
    """
    chrome_ua = BROWSER_HEADERS["User-Agent"]
    safari_ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15"

    for attempt in range(max_retries):
        sess.cookies.clear()
        sess.headers.clear()
        sess.headers.update(BROWSER_HEADERS)
        if attempt == 1:
            # Try a different UA on second attempt
            sess.headers["User-Agent"] = safari_ua

        # Step A0: land on tenant root to establish base cookies
        root_url = f"{base_url}/"
        r = sess.get(root_url, timeout=30, allow_redirects=True)
        if r.status_code == 403 and attempt + 1 < max_retries:
            time.sleep(0.8)
            continue
        r.raise_for_status()

        # Step A1: visit /webtrac/ with referer root
        webtrac_url = f"{base_url}/webtrac/"
        headers = {"Referer": root_url, **BROWSER_HEADERS}
        r = sess.get(webtrac_url, headers=headers, timeout=30, allow_redirects=True)
        if r.status_code == 403 and attempt + 1 < max_retries:
            time.sleep(0.8)
            continue
        r.raise_for_status()

        # Step A2: land on home to establish cookies/session
        home_url = f"{base_url}/webtrac/web/home.html"
        headers = {"Referer": webtrac_url, **BROWSER_HEADERS}
        time.sleep(0.4)
        r = sess.get(home_url, headers=headers, timeout=30, allow_redirects=True)
        if r.status_code == 403 and attempt + 1 < max_retries:
            time.sleep(1.0)
            continue
        r.raise_for_status()

        # Step B: request the Facility Rentals "Start" page with a Referer
        params = {"Action": "Start", "module": "FR"}
        headers = {"Referer": home_url, **BROWSER_HEADERS}
        time.sleep(0.4)
        r = sess.get(f"{base_url}{SEARCH_PATH}", params=params, headers=headers, timeout=30, allow_redirects=True)
        if r.status_code == 403:
            # Some tenants insist on SubAction too; try again with it and a short wait
            time.sleep(0.8)
            params = {"Action": "Start", "SubAction": "", "module": "FR"}
            r = sess.get(f"{base_url}{SEARCH_PATH}", params=params, headers=headers, timeout=30, allow_redirects=True)

        if r.status_code == 403 and attempt + 1 < max_retries:
            time.sleep(1.2)
            continue
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        token_input = soup.find("input", {"name": "_csrf_token"})
        if token_input and token_input.get("value"):
            return token_input["value"]

        # Fallback: some skins put it in a meta tag
        meta = soup.find("meta", {"name": "_csrf_token"})
        if meta and meta.get("content"):
            return meta["content"]

        raise RuntimeError("CSRF token not found on Start page")

def browser_bootstrap_and_get_token(
    sess: requests.Session,
    base_url: str = BASE,
    headless: bool = True,
    verbose: bool = False,
    screenshot_dir: Optional[str] = None,
) -> Tuple[str, str]:
    """Use a real browser (Playwright) to bypass stricter WAFs.

    - Navigates root -> /webtrac/ -> /webtrac/web/home.html -> Start page
    - Extracts _csrf_token from DOM
    - Transfers cookies into the provided requests session
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        raise RuntimeError("Playwright not installed. pip install playwright && playwright install") from e

    with sync_playwright() as p:
        if verbose:
            print("[browser] launching Chromium headless=%s" % headless)
        browser = p.chromium.launch(headless=headless, slow_mo=200 if verbose and not headless else 0)
        ctx = browser.new_context(user_agent=BROWSER_HEADERS["User-Agent"], locale="en-US")
        page = ctx.new_page()
        if verbose:
            page.on("console", lambda msg: print(f"[browser-console] {msg.type}: {msg.text}"))

        def snap(name: str):
            if screenshot_dir:
                try:
                    path = f"{screenshot_dir.rstrip('/')}/{name}.png"
                    page.screenshot(path=path, full_page=True)
                    if verbose:
                        print(f"[browser] saved screenshot: {path}")
                except Exception as _e:
                    if verbose:
                        print(f"[browser] screenshot failed: {name}: {_e}")

        root_url = f"{base_url}/"
        if verbose:
            print(f"[browser] goto {root_url}")
        page.goto(root_url, wait_until="domcontentloaded")
        snap("step_1_root")

        wt_url = f"{base_url}/webtrac/"
        if verbose:
            print(f"[browser] goto {wt_url}")
        page.goto(wt_url, wait_until="domcontentloaded")
        snap("step_2_webtrac")

        home_url = f"{base_url}/webtrac/web/home.html"
        if verbose:
            print(f"[browser] goto {home_url}")
        page.goto(home_url, wait_until="domcontentloaded")
        snap("step_3_home")

        # Request Start page
        start_url = f"{base_url}{SEARCH_PATH}?Action=Start&module=FR"
        if verbose:
            print(f"[browser] goto {start_url}")
        page.goto(start_url, wait_until="domcontentloaded")
        snap("step_4_start")

        # Extract token
        if verbose:
            print("[browser] extracting _csrf_token")
        token = page.locator('input[name="_csrf_token"]').first.input_value(timeout=5000)
        if not token:
            # Try meta
            token = page.locator('meta[name="_csrf_token"]').first.get_attribute("content") or ""
        if not token:
            raise RuntimeError("CSRF token not found via browser")
        if verbose:
            print("[browser] token acquired")

        # Transfer cookies to requests session
        cookies = ctx.cookies()
        for c in cookies:
            sess.cookies.set(
                name=c.get("name"),
                value=c.get("value"),
                domain=c.get("domain").lstrip("."),
                path=c.get("path", "/"),
            )

        if verbose:
            print("[browser] closing")
        browser.close()
        return token, start_url

def load_vendor_site_config(vendor: str, site: str) -> Dict:
    cfg_path = os.path.join(os.path.dirname(__file__), "config_webtrac.json")
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg.get(vendor, {}).get(site, {})

def playwright_fetch_listing_html(
    date_ymd: str,
    headless: bool = True,
    verbose: bool = False,
    screenshot_dir: Optional[str] = None,
    vendor: str = "WebTrac",
    site: str = "Burlingame",
    extra_params: Optional[Dict] = None,
) -> Tuple[str, List[Dict]]:
    """Drive the UI to select date and Tennis Court class, then capture listing HTML.

    Returns (html, cookies_as_dicts)
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        raise RuntimeError("Playwright not installed. pip install playwright && playwright install") from e

    date_obj = datetime.strptime(date_ymd, "%Y-%m-%d")
    date_str = date_obj.strftime("%m/%d/%Y")

    with sync_playwright() as p:
        if verbose:
            print("[browser] launching Chromium headless=%s" % headless)
        browser = p.chromium.launch(headless=headless, slow_mo=200 if verbose and not headless else 0)
        ctx = browser.new_context(user_agent=BROWSER_HEADERS["User-Agent"], locale="en-US")
        page = ctx.new_page()
        if verbose:
            page.on("console", lambda msg: print(f"[browser-console] {msg.type}: {msg.text}"))

        def snap(name: str):
            if screenshot_dir:
                try:
                    path = f"{screenshot_dir.rstrip('/')}/{name}.png"
                    page.screenshot(path=path, full_page=True)
                    if verbose:
                        print(f"[browser] saved screenshot: {path}")
                except Exception as _e:
                    if verbose:
                        print(f"[browser] screenshot failed: {name}: {_e}")

        # Navigate to Start page
        # Apply vendor/site config
        cfg = load_vendor_site_config(vendor, site)
        base = cfg.get("base_url").rstrip("/")
        start_url = f"{base}{SEARCH_PATH}?Action=Start&module=FR"
        if verbose:
            print(f"[browser] goto {start_url}")
        page.goto(start_url, wait_until="domcontentloaded")
        snap("listing_start")

        # Build listing URL by submitting query parameters like the form would
        # We need a fresh CSRF token from the DOM
        token = page.locator('input[name="_csrf_token"]').first.input_value(timeout=5000)
        # Build query params using config defaults with overrides
        config_params = cfg.get("params", {})
        defaults = {
            "display": config_params.get("display", "Listing"),
            "blockstodisplay": config_params.get("blockstodisplay", 50),
            "frclass": config_params.get("frclass", "Tennis Court"),
            "type": config_params.get("type", ""),
            "keywordoption": config_params.get("keywordoption", "Match One"),
        }
        params = {
            "Action": "Start",
            "SubAction": "",
            "_csrf_token": token,
            "date": date_str,
            "begintime": "12:00 am",
            "type": defaults["type"],
            "subtype": "",
            "category": "",
            "features": "",
            "location": "",
            "keyword": "",
            "keywordoption": defaults["keywordoption"],
            "blockstodisplay": defaults["blockstodisplay"],
            "frheadcount": 0,
            "frclass": defaults["frclass"],
            "primarycode": "",
            "features1": "", "features2": "", "features3": "", "features4": "",
            "features5": "", "features6": "", "features7": "", "features8": "",
            "display": defaults["display"],
            "module": "FR",
            "multiselectlist_value": "",
        }
        
        # Add any additional parameters from config (like search=yes, page=1, etc.)
        for key, value in config_params.items():
            if key not in defaults:
                params[key] = value
        if extra_params:
            params.update(extra_params)
        list_url = f"{base}{SEARCH_PATH}?{urlencode(params)}"
        if verbose:
            print(f"[browser] navigate listing -> {list_url}")
        page.goto(list_url, wait_until="domcontentloaded")
        snap("after_search")

        html = page.content()
        # Optionally save raw HTML for debugging
        if screenshot_dir:
            try:
                html_path = f"{screenshot_dir.rstrip('/')}/listing.html"
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html)
                if verbose:
                    print(f"[browser] saved html: {html_path}")
            except Exception as _e:
                if verbose:
                    print(f"[browser] save html failed: {_e}")
        cookies = ctx.cookies()
        browser.close()
        return html, cookies
    raise RuntimeError("Failed to pass WAF and obtain CSRF token after retries")


# fetch_iteminfo removed - parser already extracts all needed data

def fetch_schedule(date_ymd: str, use_browser: bool = False, headful: bool = False, debug_browser: bool = False, screenshot_dir: Optional[str] = None, query_mode: str = "burlingame") -> List[Dict]:
    """
    High-level orchestrator:
      - get token
      - fetch listing for date+locations
      - parse items and enrich with item info
    """
    sess = requests.Session()
    
    # Get base URL from config based on query_mode
    vendor = "WebTrac"
    if "san_mateo" in query_mode:
        site = "San Mateo"
    elif "albany" in query_mode:
        site = "Albany"
    else:
        site = "Burlingame"
    cfg = load_vendor_site_config(vendor, site)
    base_url = cfg.get("base_url", BASE).rstrip("/")

    # Drive the UI to produce the listing and parse directly from browser HTML
    html, cookies = playwright_fetch_listing_html(
        date_ymd,
        headless=not headful,
        verbose=debug_browser,
        screenshot_dir=screenshot_dir,
        vendor="WebTrac",
        site=site,
    )
    # Transfer cookies to requests session for iteminfo fetches
    for c in cookies:
        sess.cookies.set(
            name=c.get("name"),
            value=c.get("value"),
            domain=c.get("domain").lstrip("."),
            path=c.get("path", "/"),
        )
    # Prefer table-based parser if present, fallback to group parser
    items = parse_listing_table_schedules(html)
    if not items:
        items = parse_listing_group_schedules(html)
    for it in items:
        it.update({
            "date": date_ymd,
            "source": f"{base_url.split('//')[1].split('.')[0]}_webtrac",
        })
    return items


def main():
    ap = argparse.ArgumentParser(description="Fetch WebTrac tennis-court schedules for multiple cities.")
    ap.add_argument("--date", required=True, help="Date in YYYY-MM-DD (local), e.g. 2025-10-06")
    ap.add_argument("--out", default="-", help="Output JSON path (default stdout)")
    ap.add_argument("--use_browser", action="store_true", help="Force browser bootstrap for CSRF (Playwright)")
    ap.add_argument("--headful", action="store_true", help="Show browser window during bootstrap")
    ap.add_argument("--debug_browser", action="store_true", help="Verbose browser step logs and console mirroring")
    ap.add_argument("--screenshot_dir", type=str, default="", help="Directory to save browser screenshots per step")
    ap.add_argument("--query_mode", type=str, default="burlingame", choices=["burlingame", "san_mateo", "albany"], help="Preset of query params per tenant")
    args = ap.parse_args()

    schedules = fetch_schedule(
        args.date,
        use_browser=args.use_browser,
        headful=args.headful,
        debug_browser=args.debug_browser,
        screenshot_dir=(args.screenshot_dir or None),
        query_mode=args.query_mode,
    )

    out = json.dumps(schedules, ensure_ascii=False, indent=2)
    if args.out == "-" or not args.out:
        print(out)
    else:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out)

if __name__ == "__main__":
    main()
