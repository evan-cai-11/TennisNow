#!/usr/bin/env python3
"""
webtrac_burlingame_schedule.py

Fetch daily tennis-court schedules from Burlingame's WebTrac:
- Finds available vs unavailable time slots for each court
- Enriches each court with name + address from the Item Details page

Usage examples:
  python webtrac_burlingame_schedule.py --date 2025-10-06 --locations "Laguna,Ray Park"
  python webtrac_burlingame_schedule.py --date 2025-10-06 --locations "Washington"

Notes:
- Be gentle: WebTrac is a shared parks system. Keep request rates low.
- This scrapes public info shown on the results & item pages.
- If Burlingame changes templates, you may need to tweak selectors.
"""

import argparse
import json
import re
import time
from datetime import datetime
from typing import Dict, List, Tuple, Optional

import requests
from bs4 import BeautifulSoup, NavigableString

BASE = "https://caburlingameweb.myvscloud.com"
SEARCH_PATH = "/webtrac/web/search.html"
ITEMINFO_PATH = "/webtrac/web/iteminfo.html"

HEADERS = {
    "User-Agent": "CourtFinder/0.1 (+https://example.com/contact)",
    "Accept-Language": "en-US,en;q=0.9",
}

TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\s*(?:am|pm)\s*-\s*\d{1,2}:\d{2}\s*(?:am|pm)\b", re.I)

def get_csrf_token(sess: requests.Session) -> str:
    """
    Load the Facility Search start page to get a fresh CSRF token.
    """
    url = f"{BASE}{SEARCH_PATH}"
    # Minimal query to land on Facility Rentals search with form present.
    params = {"Action": "Start", "module": "FR"}
    r = sess.get(url, params=params, headers=HEADERS, timeout=30)
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

def search_results_html(
    sess: requests.Session, date_str: str, locations_csv: str, csrf_token: str
) -> str:
    """
    Request the 'Listing' view of Facility Search for Tennis Courts on the given date & locations.
    """
    url = f"{BASE}{SEARCH_PATH}"
    params = {
        "Action": "Start",
        "SubAction": "",
        "_csrf_token": csrf_token,
        "date": date_str,               # e.g. 10/06/2025
        "begintime": "12:00 am",
        "type": "",
        "subtype": "",
        "category": "",
        "features": "",
        "location": locations_csv,      # e.g. "Laguna,Ray Park" or "Washington"
        "keyword": "",
        "keywordoption": "Match One",
        "blockstodisplay": 50,
        "frheadcount": 0,
        "frclass": "Tennis Court",
        "primarycode": "",
        "features1": "", "features2": "", "features3": "", "features4": "",
        "features5": "", "features6": "", "features7": "", "features8": "",
        "display": "Listing",
        "module": "FR",
        "multiselectlist_value": "",
    }
    r = sess.get(url, params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text

def parse_listing_into_items(html: str) -> List[Dict]:
    """
    Parse the Facility Search listing page.
    Strategy:
      - Find each 'Item Details' link (contains FMID) -> one facility "item"
      - For each item, scan forward through DOM until the next item; collect
        the 'Book Now:' line's time-slot anchors (available) and any 'Unavailable' text
    """
    soup = BeautifulSoup(html, "html.parser")
    items = []
    # Each facility has an Item Details link like iteminfo.html?FMID=296964&Module=FR
    for a in soup.select('a[href*="iteminfo.html?"][href*="FMID="]'):
        href = a.get("href", "")
        # Normalize absolute/relative
        fmid_match = re.search(r"[?&]FMID=(\d+)", href)
        if not fmid_match:
            continue
        fmid = fmid_match.group(1)

        # Walk forward from this anchor to find the nearest "Book Now:" segment
        available = []
        unavailable = []
        # Iterate until the next Item Details link or end
        el = a
        while True:
            el = el.next_elements.__self__.next_element if hasattr(el, "next_element") else None  # type: ignore
            if el is None:
                break
            # Stop when next facility's Item Details appears
            if getattr(el, "name", None) == "a" and el.has_attr("href") and "iteminfo.html" in el["href"]:
                break
            # Collect time-slot links
            if getattr(el, "name", None) == "a":
                txt = el.get_text(strip=True)
                if TIME_RE.fullmatch(txt):
                    available.append(txt)
            # Collect "Unavailable" markers that appear as bare text between links
            if isinstance(el, NavigableString):
                text = str(el).strip()
                # e.g., "... 5:00 pm - 6:00 pm Unavailable 6:00 pm - 7:00 pm ..."
                if "Unavailable" in text:
                    # Attempt to capture the time that precedes "Unavailable" on the same line
                    # This is heuristic; we also record a generic marker.
                    m = TIME_RE.search(text)
                    if m:
                        unavailable.append(m.group(0))
                    else:
                        unavailable.append("Unavailable (unspecified slot)")
        items.append({"fmid": fmid, "available_slots": available, "unavailable_slots": unavailable})
    return items

def fetch_iteminfo(sess: requests.Session, fmid: str) -> Dict[str, Optional[str]]:
    """
    Load the Item Details page for a court to get its human name and address.
    """
    url = f"{BASE}{ITEMINFO_PATH}"
    params = {"FMID": fmid, "Module": "FR"}
    r = sess.get(url, params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # Name appears in a heading like "Details for Laguna Park Court 1"
    title = soup.find(string=re.compile(r"^Details\s+for\s+", re.I))
    name = None
    if title:
        name = re.sub(r"^Details\s+for\s+", "", title.strip(), flags=re.I)

    # Address appears near "Location Details <Venue Name> 1416 Laguna Ave Burlingame, CA, 94010"
    address = None
    loc_hdr = soup.find(string=re.compile(r"Location Details", re.I))
    if loc_hdr:
        # The address is often in the same parent or the next element
        # Extract a compact string from that block
        blk = loc_hdr.parent.get_text(" ", strip=True)
        # Remove the "Location Details" label
        blk = re.sub(r"^\s*Location Details\s*", "", blk, flags=re.I)
        address = blk or None

    return {"name": name, "address": address}

def fetch_schedule(date_ymd: str, locations_csv: str) -> List[Dict]:
    """
    High-level orchestrator:
      - get token
      - fetch listing for date+locations
      - parse items and enrich with item info
    """
    sess = requests.Session()
    token = get_csrf_token(sess)
    # Convert YYYY-MM-DD -> MM/DD/YYYY for WebTrac
    date_obj = datetime.strptime(date_ymd, "%Y-%m-%d")
    date_str = date_obj.strftime("%m/%d/%Y")

    html = search_results_html(sess, date_str, locations_csv, token)
    items = parse_listing_into_items(html)

    results = []
    for it in items:
        time.sleep(0.3)  # be polite
        meta = fetch_iteminfo(sess, it["fmid"])
        results.append({
            "fmid": it["fmid"],
            "name": meta.get("name"),
            "address": meta.get("address"),
            "date": date_ymd,
            "location_filter": locations_csv,
            "available": it["available_slots"],
            "unavailable": it["unavailable_slots"],
            "source": "burlingame_webtrac"
        })
    return results

def main():
    ap = argparse.ArgumentParser(description="Fetch Burlingame WebTrac tennis-court schedules.")
    ap.add_argument("--date", required=True, help="Date in YYYY-MM-DD (local), e.g. 2025-10-06")
    ap.add_argument("--locations", required=True,
                    help='Comma-separated list as shown by the site, e.g. "Laguna,Ray Park" or "Washington"')
    ap.add_argument("--out", default="-", help="Output JSON path (default stdout)")
    args = ap.parse_args()

    schedules = fetch_schedule(args.date, args.locations)

    out = json.dumps(schedules, ensure_ascii=False, indent=2)
    if args.out == "-" or not args.out:
        print(out)
    else:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out)

if __name__ == "__main__":
    main()
