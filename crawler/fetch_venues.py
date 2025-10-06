#!/usr/bin/env python3
"""
fetch_tennis_courts.py

Fetch public tennis-court venues for a given US city or county using OpenStreetMap (Overpass).

Usage:
  python fetch_tennis_courts.py --place "San Mateo County, California"
  python fetch_tennis_courts.py --place "Burlingame, CA" --csv courts.csv
  python fetch_tennis_courts.py --place "King County, Washington" --strict-public

Notes:
- You MUST provide a valid contact in --contact (email or URL) per OSM/Nominatim usage policy.
- Results are heuristic for "public". Review `looks_public()` to tune.
"""

from __future__ import annotations
import argparse, csv, json, sys, time, random, logging
from typing import Any, Dict, List, Optional, Tuple
import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]

def backoff_sleep(try_idx: int) -> None:
    # 0.5, 1, 2, 4, ... + jitter
    time.sleep((0.5 * (2 ** try_idx)) + random.random() * 0.3)

def http_get_json(url: str, params: Dict[str, Any], headers: Dict[str, str], max_retries: int = 5) -> Dict[str, Any]:
    for i in range(max_retries):
        r = requests.get(url, params=params, headers=headers, timeout=30)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 502, 503, 504):
            backoff_sleep(i)
            continue
        raise RuntimeError(f"GET {url} failed: {r.status_code} {r.text[:200]}")
    raise RuntimeError(f"GET {url} failed after {max_retries} retries")

def geocode_place(place: str, contact: str) -> Dict[str, Any]:
    headers = {"User-Agent": f"CourtFinder/0.1 ({contact})"}
    params = {
        "q": place,
        "format": "json",
        "addressdetails": 1,
        "limit": 1,
        "extratags": 1,
        "countrycodes": "us",
    }
    data = http_get_json(NOMINATIM_URL, params, headers)
    if not data:
        raise ValueError(f"Place not found: {place}")
    item = data[0]
    return item

def osm_area_id_from_nominatim(item: Dict[str, Any]) -> Optional[int]:
    """
    Overpass area ID = 3600000000 + OSM relation id (most cities/counties are relations).
    If not a relation, return None (we'll fallback to BBOX).
    """
    osm_type = item.get("osm_type")
    osm_id = int(item.get("osm_id"))
    if osm_type == "relation":
        return 3600000000 + osm_id
    return None

def bbox_from_nominatim(item: Dict[str, Any]) -> Tuple[float, float, float, float]:
    # [south, north, west, east]
    bbox = item.get("boundingbox")
    south, north, west, east = map(float, bbox)
    return south, west, north, east

def build_overpass_query_by_area(area_id: int) -> str:
    # Grab all OSM elements tagged sport=tennis; output tags + center (centroid for ways/relations)
    return f"""
[out:json][timeout:60];
area({area_id})->.searchArea;
(
  node["sport"="tennis"](area.searchArea);
  way["sport"="tennis"](area.searchArea);
  relation["sport"="tennis"](area.searchArea);
);
out tags center;
"""

def build_overpass_query_by_bbox(south: float, west: float, north: float, east: float) -> str:
    return f"""
[out:json][timeout:60];
(
  node["sport"="tennis"]({south},{west},{north},{east});
  way["sport"="tennis"]({south},{west},{north},{east});
  relation["sport"="tennis"]({south},{west},{north},{east});
);
out tags center;
"""

def fetch_overpass(query: str, contact: str) -> Dict[str, Any]:
    headers = {"User-Agent": f"CourtFinder/0.1 ({contact})", "Accept-Encoding": "gzip"}
    last_err = None
    for idx, url in enumerate(OVERPASS_ENDPOINTS):
        try:
            r = requests.post(url, data=query.encode("utf-8"), headers=headers, timeout=90)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 502, 503, 504):
                backoff_sleep(idx)
                continue
            last_err = RuntimeError(f"Overpass error {r.status_code}: {r.text[:200]}")
        except Exception as e:
            last_err = e
        backoff_sleep(idx)
    raise last_err or RuntimeError("Overpass request failed")

def elem_lat_lon(elem: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    if elem.get("type") == "node":
        return elem.get("lat"), elem.get("lon")
    center = elem.get("center") or {}
    return center.get("lat"), center.get("lon")

def looks_public(tags: Dict[str, str], strict: bool=False) -> bool:
    """
    Heuristic:
    - Exclude explicit private: access=private/no, club=yes, membership=*, operator:type=private
    - Exclude fee=members|permit when strict
    - Prefer access in {yes, permissive, public}
    - Schools often map as pitches inside school grounds; many have access=private (filtered). Some may slip through.
    """
    access = (tags.get("access") or "").lower()
    if access in {"private", "no"}:
        return False
    if (tags.get("club") or "").lower() == "yes":
        return False
    if (tags.get("membership") or "").lower() in {"yes", "members", "members_only"}:
        return False
    if (tags.get("operator:type") or "").lower() == "private":
        return False
    if strict:
        fee = (tags.get("fee") or "").lower()
        if fee in {"yes", "members", "permit"}:
            return False
    # If explicitly public/permissive, good.
    if access in {"public", "permissive", "yes"}:
        return True
    # Otherwise assume public if not obviously private.
    return True

def normalize_record(elem: Dict[str, Any], strict_public: bool) -> Optional[Dict[str, Any]]:
    tags = elem.get("tags", {}) or {}
    if not looks_public(tags, strict=strict_public):
        return None
    lat, lon = elem_lat_lon(elem)
    if lat is None or lon is None:
        return None
    # Compose a best-effort venue name
    name = tags.get("name")
    if not name:
        # Try to infer from operator or context
        op = tags.get("operator")
        if op:
            name = f"{op} Tennis Courts"
        else:
            name = "Public Tennis Courts"

    # Surface/lights hints
    surface = tags.get("surface") or tags.get("court:surface") or tags.get("surface:tennis")
    lit = tags.get("lit") or tags.get("lighting")
    lights = None
    if lit:
        lights = lit.lower() in {"yes", "true", "1"}

    record = {
        "osm_type": elem.get("type"),
        "osm_id": elem.get("id"),
        "name": name,
        "lat": lat,
        "lon": lon,
        "is_public_guess": True,
        "surface": surface,
        "lights": lights,
        "indoor": (tags.get("indoor") or "").lower() in {"yes", "true", "1"},
        "num_courts": _guess_num_courts(tags),
        "address": {
            "city": tags.get("addr:city"),
            "county": tags.get("addr:county"),
            "state": tags.get("addr:state"),
            "postcode": tags.get("addr:postcode"),
        },
        "tags": tags,  # keep raw for debugging/enrichment
    }
    return record

def _guess_num_courts(tags: Dict[str, str]) -> Optional[int]:
    for k in ("capacity:tennis", "capacity:courts", "capacity", "courts", "tennis:courts"):
        v = tags.get(k)
        if v and v.isdigit():
            return int(v)
    return None

def to_csv(path: str, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        with open(path, "w", newline="", encoding="utf-8") as f:
            f.write("")  # empty file
        return
    # Flatten a few fields
    fieldnames = ["name", "lat", "lon", "num_courts", "surface", "lights",
                  "indoor", "osm_type", "osm_id", "addr_city", "addr_county", "addr_state", "addr_postcode"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({
                "name": r["name"],
                "lat": r["lat"],
                "lon": r["lon"],
                "num_courts": r.get("num_courts"),
                "surface": r.get("surface"),
                "lights": r.get("lights"),
                "indoor": r.get("indoor"),
                "osm_type": r.get("osm_type"),
                "osm_id": r.get("osm_id"),
                "addr_city": (r.get("address") or {}).get("city"),
                "addr_county": (r.get("address") or {}).get("county"),
                "addr_state": (r.get("address") or {}).get("state"),
                "addr_postcode": (r.get("address") or {}).get("postcode"),
            })

def main():
    ap = argparse.ArgumentParser(description="Fetch public tennis courts from OSM for a US city or county.")
    ap.add_argument("--place", required=True, help='e.g. "San Mateo County, California" or "Burlingame, CA"')
    ap.add_argument("--csv", help="Write results to CSV file (optional)")
    ap.add_argument("--json", help="Write results to JSON file (optional)")
    ap.add_argument("--strict-public", action="store_true",
                    help="Stricter filter (excludes fee=*, permit/members-only).")
    ap.add_argument("--contact", required=True,
                    help="Contact string for User-Agent (email or URL), required by OSM/Nominatim.")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    logging.info("Geocoding place: %s", args.place)
    place = geocode_place(args.place, args.contact)
    display_name = place.get("display_name")
    area_id = osm_area_id_from_nominatim(place)
    logging.info("Found: %s (osm_type=%s, osm_id=%s)%s",
                 display_name, place.get("osm_type"), place.get("osm_id"),
                 f", area_id={area_id}" if area_id else " (will use bbox)")

    if area_id:
        query = build_overpass_query_by_area(area_id)
    else:
        south, west, north, east = bbox_from_nominatim(place)
        logging.info("Using bounding box: S=%s W=%s N=%s E=%s", south, west, north, east)
        query = build_overpass_query_by_bbox(south, west, north, east)

    logging.info("Querying Overpass…")
    data = fetch_overpass(query, args.contact)
    elements = data.get("elements", [])
    logging.info("Fetched %d tennis features", len(elements))

    records: List[Dict[str, Any]] = []
    for e in elements:
        rec = normalize_record(e, strict_public=args.strict_public)
        if rec:
            records.append(rec)

    logging.info("After public filter: %d venues", len(records))

    # Default output: JSON to stdout (pretty)
    if not args.csv and not args.json:
        json.dump(records, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        logging.info("Wrote JSON: %s", args.json)
    if args.csv:
        to_csv(args.csv, records)
        logging.info("Wrote CSV: %s", args.csv)

if __name__ == "__main__":
    main()
