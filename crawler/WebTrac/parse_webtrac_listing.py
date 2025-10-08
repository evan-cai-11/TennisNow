#!/usr/bin/env python3
"""
Pure HTML parsers for WebTrac Facility Search (Listing view).

Exports:
- parse_listing_table_schedules(html: str) -> List[dict]
- parse_listing_group_schedules(html: str) -> List[dict]

CLI:
  python parse_webtrac_listing.py --in path/to/listing.html --out schedules.json
"""

import argparse
import json
import re
from typing import Dict, List

from bs4 import BeautifulSoup, NavigableString

TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\s*(?:am|pm)\s*-\s*\d{1,2}:\d{2}\s*(?:am|pm)\b", re.I)


def parse_listing_group_schedules(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    container = soup.find(id="frwebsearch_nextgencontrolsgroup")
    if not container:
        return []
    results: List[Dict] = []
    for card in container.select(".result-content"):
        # fmid from Item Details link when present
        fmid = None
        link = card.select_one('a[href*="iteminfo.html?"][href*="FMID="]')
        if link and link.has_attr("href"):
            m = re.search(r"[?&]FMID=(\d+)", link["href"])  # type: ignore[index]
            if m:
                fmid = m.group(1)

        # Facility label from header structure
        label = None
        header = card.select_one('.header.result-header .result-header__info h2 span')
        if header and header.get_text(strip=True):
            label = header.get_text(strip=True)

        # Location best-effort: try Location Description field if present near card
        location = None
        loc_label = card.find("td", attrs={"data-title": "Location Description"})
        if loc_label:
            location = loc_label.get_text(strip=True)

        available: List[str] = []
        unavailable: List[str] = []
        for a in card.select("a.cart-button"):
            classes = " ".join(a.get("class", [])).lower()
            tooltip = a.get("data-tooltip", "").lower()
            
            # Available slots: have "success" class and "Book Now" tooltip
            if "success" in classes and "book now" in tooltip:
                time_txt = a.get_text(strip=True)
                if TIME_RE.fullmatch(time_txt):
                    available.append(time_txt)
            
            # Unavailable slots: have "error" class and "Unavailable" tooltip
            elif "error" in classes and "unavailable" in tooltip:
                spans = a.find_all("span")
                if spans:
                    time_txt = spans[0].get_text(strip=True)
                    if TIME_RE.fullmatch(time_txt):
                        unavailable.append(time_txt)

        results.append({
            "fmid": fmid,
            "label": label,
            "location": location,
            "available_slots": available,
            "unavailable_slots": unavailable,
        })
    return results


def parse_listing_table_schedules(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="frwebsearch_output_table")
    if not table:
        return []
    tbody = table.find("tbody")
    if not tbody:
        return []

    rows = tbody.find_all("tr", recursive=False)
    results: List[Dict] = []
    i = 0
    while i < len(rows):
        row = rows[i]
        label_cells = row.find_all("td", class_="label-cell")
        if not label_cells:
            i += 1
            continue
        facility = None
        location = None
        fmid = None
        for td in label_cells:
            title = td.get("data-title", "")
            if title == "Facility Description" and not facility:
                facility = td.get_text(strip=True)
            elif title == "Location Description" and not location:
                location = td.get_text(strip=True)
        details_link = row.find("a", href=re.compile(r"iteminfo\.html\?", re.I))
        if details_link and details_link.has_attr("href"):
            m = re.search(r"[?&]FMID=(\d+)", details_link["href"])  # type: ignore[index]
            if m:
                fmid = m.group(1)

        available: List[str] = []
        unavailable: List[str] = []
        if i + 1 < len(rows):
            cart_row = rows[i + 1]
            for a in cart_row.select("a.cart-button"):
                classes = " ".join(a.get("class", [])).lower()
                tooltip = a.get("data-tooltip", "").lower()
                
                # Available slots: have "success" class and "Book Now" tooltip
                if "success" in classes and "book now" in tooltip:
                    time_txt = a.get_text(strip=True)
                    if TIME_RE.fullmatch(time_txt):
                        available.append(time_txt)
                
                # Unavailable slots: have "error" class and "Unavailable" tooltip
                elif "error" in classes and "unavailable" in tooltip:
                    spans = a.find_all("span")
                    if spans:
                        time_txt = spans[0].get_text(strip=True)
                        if TIME_RE.fullmatch(time_txt):
                            unavailable.append(time_txt)

        results.append({
            "fmid": fmid,
            "label": facility,
            "location": location,
            "available_slots": available,
            "unavailable_slots": unavailable,
        })
        i += 2

    return results


def main():
    ap = argparse.ArgumentParser(description="Parse WebTrac Facility Listing HTML -> JSON schedules")
    ap.add_argument("--in", dest="infile", required=True, help="Input HTML file")
    ap.add_argument("--out", dest="outfile", required=True, help="Output JSON file")
    args = ap.parse_args()

    with open(args.infile, "r", encoding="utf-8") as f:
        html = f.read()

    items = parse_listing_table_schedules(html)
    if not items:
        items = parse_listing_group_schedules(html)

    with open(args.outfile, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"Wrote {args.outfile} ({len(items)} items)")


if __name__ == "__main__":
    main()


