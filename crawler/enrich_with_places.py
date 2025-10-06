#!/usr/bin/env python3
# enrich_with_places.py
# Input: OSM-derived JSON from your fetch script
# Output: same objects, plus {google: {place_id, displayName, formattedAddress, accessibilityOptions}}
#
# Requires: pip install requests rapidfuzz

import os, time, json, requests, math, re
from typing import List, Optional
from rapidfuzz import fuzz

PLACES_BASE = "https://places.googleapis.com/v1"
API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")  # set this in your env

DEFAULT_BROAD_TERMS = [
    "tennis",
    "court",
    "courts",
    "club",
    "park",
    "school",
    "recreation",
    "rec",
    "sports center",
    "sports centre",
]

# Minimal allowlist of valid Google Place types we intend to use with Nearby.
# Refer to Google docs for the full list; we only include what we need.
VALID_NEARBY_TYPES = {
    "park",
    "school",
    "community_center",
    "stadium",
    "university",
    "tourist_attraction",
}

# Phrase → official type mapping for Nearby filters
PHRASE_TO_TYPE = {
    "recreation center": "community_center",
    "event venue": "stadium",
}

def haversine_m(lat1, lon1, lat2, lon2):
    R=6371000.0
    dlat=math.radians(lat2-lat1); dlon=math.radians(lon2-lon1)
    a=math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return 2*R*math.asin(math.sqrt(a))

def norm_name(s:str) -> str:
    s = (s or "").lower()
    s = re.sub(r'\b(tennis|courts?|park|recreation|rec|center|centre)\b', '', s)
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

def _build_text_query(keyword: str, broad_terms: List[str]) -> str:
    # If a keyword is given, prefer it but append broad terms to widen recall
    if keyword:
        # ensure keyword is included once; append some broad terms for recall
        extra = " ".join(sorted(set(t for t in broad_terms if t not in keyword.lower())))
        return f"{keyword} {extra}".strip()
    # No keyword: use broad terms only
    return " ".join(broad_terms)

def places_nearby(
    lat,
    lng,
    radius_m=120,
    keyword="tennis court",
    verbose=False,
    broad_terms: Optional[List[str]] = None
):
    """Return nearby candidates.

    If keyword is provided, use searchText with a locationBias.
    If keyword is falsy, use searchNearby ranked by distance with no type filter.
    """
    # Decide which API to use
    url = f"{PLACES_BASE}/places:searchText"
    headers = {
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": "places.id,places.displayName,places.location,places.types"
    }

    terms = broad_terms or DEFAULT_BROAD_TERMS
    text_query = _build_text_query(keyword, terms)
    payload = {
        "textQuery": text_query,
        "locationBias": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": radius_m
            }
        },
        "maxResultCount": 10,
        "rankPreference": "DISTANCE"
    }

    try:
        if verbose:
            mode = 'searchText' 
            print(f"[places_nearby] lat={lat}, lng={lng}, radius_m={radius_m}, keyword='{text_query}' mode={mode}")

        r = requests.post(url, headers=headers, json=payload, timeout=20)
        if r.status_code != 200:
            if verbose:
                print(f"[places_nearby] HTTP {r.status_code}: {r.text[:300]}...")
            return []
        resp = r.json()
        places = resp.get("places", [])
        if verbose:
            print(f"[places_nearby] candidates={len(places)}")
        return places
    except requests.RequestException as e:
        if verbose:
            print(f"[places_nearby] Request failed: {e}")
        return []

def get_place_details(place_id, verbose=False):
    # Fetch only what you need at display time
    url = f"{PLACES_BASE}/places/{place_id}"
    headers = {
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": (
            "id,displayName,formattedAddress,accessibilityOptions,"
            "nationalPhoneNumber,websiteUri"
        )
    }
    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code != 200:
            if verbose:
                print(f"[get_place_details] HTTP {r.status_code} for {place_id}: {r.text[:300]}...")
            return None
        return r.json()
    except requests.RequestException as e:
        if verbose:
            print(f"[get_place_details] Request failed for {place_id}: {e}")
        return None

def choose_best_match(osm_name, lat, lng, candidates, verbose=False, prefer_distance=True, prefer_types=None, avoid_name_terms=None):
    if prefer_types is None:
        # Default preferred signals: types and common venue terms
        prefer_types = {
            "tennis court",
            "school",
            "event venue",
            "recreation center",
            "park",
            # add a few plausible Google types for extra recall
            "stadium",
            "community_center",
        }
    if avoid_name_terms is None:
        avoid_name_terms = {"academy", "shop", "store", "club", "pro shop"}
    base = norm_name(osm_name)
    best = (None, -1.0, None)  # (place, score, meters)
    for p in candidates:
        loc = p.get("location", {})
        d = haversine_m(lat, lng, loc.get("latitude", 0.0), loc.get("longitude", 0.0))
        # distance score: 100 at 0m, 0 at 120m
        dist_score = max(0, 100 * (1 - min(d, 120.0) / 120.0))
        name_score = fuzz.token_set_ratio(base, norm_name(p.get("displayName", {}).get("text")))
        if prefer_distance:
            score = dist_score
        else:
            score = 0.55 * dist_score + 0.45 * name_score if base else dist_score

        # Type-based boosts and business-name penalties
        ptypes = set(p.get("types", []) or [])
        boost = 0.0
        # Boost if any preferred type matches the official Google types
        if ptypes & set(t for t in prefer_types if t.isidentifier()):
            boost += 12.0
        pname = (p.get("displayName", {}) or {}).get("text", "")
        lower_name = (pname or "").lower()
        # Also boost if preferred terms appear in the name (handles phrases like "tennis court")
        if any(term in lower_name for term in prefer_types):
            boost += 8.0
        if any(term in lower_name for term in avoid_name_terms):
            boost -= 10.0  # downweight business-y names
        score += boost
        if score > best[1]:
            best = (p, score, d)
        if verbose:
            pname = (p.get("displayName", {}) or {}).get("text")
            print(f"[score] cand='{pname}' dist_m={round(d,1)} dist_score={round(dist_score,1)} name_score={round(name_score,1)} types={list(ptypes)} total={round(score,1)}")
    return best if best[0] else (None, 0, None)

def enrich(records, radius_m=120, threshold=70, keyword="tennis court", verbose=False, accept_within_m=200, hard_reject_over_m=400, prefer_distance=True, prefer_types=None, avoid_name_terms=None, included_types=None, excluded_types=None):
    out = []
    for r in records:
        lat, lon = r["lat"], r["lon"]
        osm_name = r.get("name")
        if verbose:
            print("\n=== Record ===")
            print(f"OSM name='{osm_name}' lat={lat} lon={lon}")
        # Query candidates (Text Search by default; Nearby when type filters are used or forced)
        cands = places_nearby(
            lat,
            lon,
            radius_m=radius_m,
            keyword=keyword,
            verbose=verbose
        )
        place, score, meters = choose_best_match(
            osm_name,
            lat,
            lon,
            cands,
            verbose=verbose,
            prefer_distance=prefer_distance,
            prefer_types=set(prefer_types or []),
            avoid_name_terms=set(avoid_name_terms or []),
        )
        # Enforce distance accept/reject regardless of score
        if place and meters is not None and meters <= accept_within_m:
            pass  # accept
        elif place and meters is not None and meters > hard_reject_over_m:
            if verbose:
                print(f"[skip] Nearest {round(meters,1)}m exceeds hard reject {hard_reject_over_m}m")
            out.append(r)
            time.sleep(0.1)
            continue
        # Fallback to threshold if within acceptable band
        if place and score >= threshold:
            details = get_place_details(place["id"], verbose=verbose)
            r["google"] = {
                "place_id": place["id"],
                # store details only transiently (show in UI; avoid long-term caching to follow Google ToS)
                "displayName": details.get("displayName", {}),
                "formattedAddress": details.get("formattedAddress"),
                "accessibilityOptions": details.get("accessibilityOptions", {}),
                "distance_m": round(meters or 0, 1),
                "match_score": round(score, 1),
            }
            if verbose:
                dname = (place.get("displayName", {}) or {}).get("text")
                print(f"[selected] place_id={place['id']} name='{dname}' distance_m={round(meters or 0,1)} score={round(score,1)}")
        else:
            if verbose:
                if not cands:
                    print("[skip] No candidates returned")
                elif not place:
                    print("[skip] No suitable place found")
                else:
                    print(f"[skip] Best score {round(score,1)} below threshold {threshold}")
        out.append(r)
        time.sleep(0.1)  # be gentle; add proper rate limiting in prod
    return out

if __name__ == "__main__":
    import argparse, sys
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="infile", required=True, help="OSM JSON file from your fetch script")
    ap.add_argument("--out", dest="outfile", required=True, help="Output JSON (enriched)")
    ap.add_argument("--verbose", action="store_true", help="Print intermediate debug info")
    ap.add_argument("--radius", type=int, default=120, help="Search radius in meters")
    ap.add_argument("--threshold", type=float, default=70.0, help="Match score threshold (0-100)")
    ap.add_argument("--keyword", type=str, default="", help="Optional search keyword; broad terms are appended automatically")
    ap.add_argument("--extra_terms", type=str, default="", help="Comma-separated extra broad terms to widen text query")
    ap.add_argument("--accept_within_m", type=float, default=200.0, help="Auto-accept nearest within meters")
    ap.add_argument("--hard_reject_over_m", type=float, default=400.0, help="Reject if nearest exceeds meters")
    ap.add_argument("--prefer_distance", action="store_true", help="Prefer pure distance for scoring")
    ap.add_argument("--prefer_types", type=str, default="park,school,university,stadium,tourist_attraction", help="Comma-separated types to boost")
    ap.add_argument("--avoid_name_terms", type=str, default="academy,shop,store,club,pro shop", help="Comma-separated name substrings to penalize")
    args = ap.parse_args()
    if not API_KEY:
        sys.exit("Set GOOGLE_MAPS_API_KEY in your env.")
    with open(args.infile, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Build broad terms for this run
    broad_terms = DEFAULT_BROAD_TERMS.copy()
    if args.extra_terms:
        for t in [s.strip() for s in args.extra_terms.split(",") if s.strip()]:
            if t not in broad_terms:
                broad_terms.append(t)

    # Prepare preferences
    prefer_types = set([s.strip() for s in (args.prefer_types or "").split(",") if s.strip()])
    avoid_name_terms = set([s.strip().lower() for s in (args.avoid_name_terms or "").split(",") if s.strip()])
    included_types = [
        "park",
        "school",
        "tennis court",
        "recreation center",  # proxy for recreation center
        "event venue"         # proxy for event venue
    ]

    excluded_types = ["shop", "store", "club", "pro shop", "academy"]

    enriched = enrich(
        data,
        radius_m=args.radius,
        threshold=args.threshold,
        keyword=args.keyword,
        verbose=args.verbose,
        accept_within_m=args.accept_within_m,
        hard_reject_over_m=args.hard_reject_over_m,
        prefer_distance=args.prefer_distance or not bool(args.keyword),
        prefer_types=prefer_types,
        avoid_name_terms=avoid_name_terms,
        included_types=included_types,
        excluded_types=excluded_types,
    )
    with open(args.outfile, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)
    print(f"Wrote {args.outfile} ({len(enriched)} rows)")
