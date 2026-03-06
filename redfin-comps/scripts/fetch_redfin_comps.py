#!/usr/bin/env python3
"""
fetch_redfin_comps.py
---------------------
Pulls recently sold comparable properties directly from Redfin's internal API.
No FireCrawl needed — zero API credits, faster, and more complete results.

Usage:
    python fetch_redfin_comps.py --address "4684 E 175th St, Cleveland, OH 44128"
    python fetch_redfin_comps.py --address "..." --lookback-days 365 --subject-beds 3 --subject-sqft 1200

Dependencies:
    pip install geopy python-dotenv requests

Environment:
    GOOGLE_MAPS_API_KEY - Optional. Falls back to free Nominatim geocoder.
"""

import argparse
import csv
import io
import json
import math
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

# ---------------------------------------------------------------------------
# Load environment
# ---------------------------------------------------------------------------
_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
if not _ENV_PATH.exists():
    _ENV_PATH = Path.cwd() / ".env"
load_dotenv(_ENV_PATH)

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

# ---------------------------------------------------------------------------
# Redfin city/state slug mapping
# Key: lowercase city name → (redfin region_id, state abbreviation, market slug)
# ---------------------------------------------------------------------------
REDFIN_CITY_MAP = {
    # Cleveland Metro
    "cleveland":          ("4145", "OH", "cleveland"),
    "lakewood":           ("10994", "OH", "cleveland"),
    "euclid":             ("10808", "OH", "cleveland"),
    "east cleveland":     ("4145", "OH", "cleveland"),
    "lyndhurst":          ("11059", "OH", "cleveland"),
    "shaker heights":     ("11363", "OH", "cleveland"),
    "cleveland heights":  ("10759", "OH", "cleveland"),
    "university heights": ("11528", "OH", "cleveland"),
    "south euclid":       ("11407", "OH", "cleveland"),
    "mayfield heights":   ("11082", "OH", "cleveland"),
    "maple heights":      ("11073", "OH", "cleveland"),
    "warrensville heights":("11547","OH", "cleveland"),
    "bedford heights":    ("10579", "OH", "cleveland"),
    "parma":              ("11255", "OH", "cleveland"),
    "parma heights":      ("11256", "OH", "cleveland"),
    "fairview park":      ("10826", "OH", "cleveland"),
    "rocky river":        ("11330", "OH", "cleveland"),
    "westlake":           ("11578", "OH", "cleveland"),
    "bay village":        ("10573", "OH", "cleveland"),
    "strongsville":       ("11450", "OH", "cleveland"),
    "north royalton":     ("11195", "OH", "cleveland"),
    "mentor":             ("11090", "OH", "cleveland"),
    "willoughby":         ("11593", "OH", "cleveland"),
    "wickliffe":          ("11583", "OH", "cleveland"),
    "willowick":          ("11594", "OH", "cleveland"),
    "brook park":         ("10660", "OH", "cleveland"),
    # Columbus Metro
    "columbus":           ("7051",  "OH", "columbus"),
    "dublin":             ("10790", "OH", "columbus"),
    "new albany":         ("11160", "OH", "columbus"),
    "upper arlington":    ("11531", "OH", "columbus"),
    "hilliard":           ("10942", "OH", "columbus"),
    "westerville":        ("11575", "OH", "columbus"),
    "worthington":        ("11621", "OH", "columbus"),
    "gahanna":            ("10851", "OH", "columbus"),
    "grove city":         ("10893", "OH", "columbus"),
    "pickerington":       ("11275", "OH", "columbus"),
    "reynoldsburg":       ("11318", "OH", "columbus"),
    "canal winchester":   ("10690", "OH", "columbus"),
    "grandview heights":  ("10879", "OH", "columbus"),
    # Dayton Metro
    "dayton":             ("8568",  "OH", "dayton"),
    "kettering":          ("10977", "OH", "dayton"),
    "oakwood":            ("11219", "OH", "dayton"),
    "moraine":            ("11132", "OH", "dayton"),
    "west carrollton":    ("11561", "OH", "dayton"),
    # Akron Metro
    "akron":              ("10379", "OH", "akron"),
    "cuyahoga falls":     ("10769", "OH", "akron"),
    "stow":               ("11443", "OH", "akron"),
    "fairlawn":           ("10822", "OH", "akron"),
    "hudson":             ("10956", "OH", "akron"),
    "silver lake":        ("11384", "OH", "akron"),
    "tallmadge":          ("11464", "OH", "akron"),
    "barberton":          ("10566", "OH", "akron"),
    "munroe falls":       ("11143", "OH", "akron"),
}

# Redfin region_type for cities = 6, ZIP codes = 2
REGION_TYPE_CITY = 6
REGION_TYPE_ZIP  = 2

# HTTP headers that mimic a real browser — required to avoid Redfin 403s
REDFIN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.redfin.com/",
    "Origin": "https://www.redfin.com",
}

# ---------------------------------------------------------------------------
# Geocoding
# ---------------------------------------------------------------------------

def geocode_address(address: str) -> tuple:
    """Returns (lat, lon, city, state, zip)."""
    if GOOGLE_MAPS_API_KEY:
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        resp = requests.get(url, params={"address": address, "key": GOOGLE_MAPS_API_KEY}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data["status"] == "OK":
            result = data["results"][0]
            loc = result["geometry"]["location"]
            components = {c["types"][0]: c["long_name"] for c in result["address_components"]}
            short_state = next(
                (c["short_name"] for c in result["address_components"]
                 if "administrative_area_level_1" in c["types"]), ""
            )
            return (
                loc["lat"], loc["lng"],
                components.get("locality", components.get("sublocality", "")),
                short_state,
                components.get("postal_code", ""),
            )
        print(f"[WARN] Google Maps geocoding failed: {data['status']}", file=sys.stderr)

    geolocator = Nominatim(user_agent="homebuyerplus-comps/1.0")
    try:
        location = geolocator.geocode(address, addressdetails=True, timeout=10)
    except (GeocoderTimedOut, GeocoderServiceError) as e:
        raise RuntimeError(f"Geocoding failed: {e}") from e
    if not location:
        raise RuntimeError(f"Could not geocode address: '{address}'")
    raw = location.raw.get("address", {})
    city = raw.get("city") or raw.get("town") or raw.get("village") or raw.get("suburb") or ""
    state = raw.get("ISO3166-2-lvl4", "").replace("US-", "")
    zipcode = raw.get("postcode", "")
    return location.latitude, location.longitude, city, state, zipcode


# ---------------------------------------------------------------------------
# Neighborhood lookup (Cleveland SPAs)
# ---------------------------------------------------------------------------

_NBHD_REF_PATH = Path(__file__).resolve().parent.parent / "references" / "cleveland_neighborhoods.json"

CONDITION_TIERS = [
    "major-rehab",      # bottom quintile $/sqft
    "minor-rehab",
    "turnkey-low",
    "turnkey-average",
    "turnkey-high",     # top quintile $/sqft
]

CONDITION_LABELS = {
    "major-rehab":    "Major Rehab Needed",
    "minor-rehab":    "Minor Rehab Needed",
    "turnkey-low":    "Turnkey Low End",
    "turnkey-average":"Turnkey Average",
    "turnkey-high":   "Turnkey High End",
}


def load_neighborhoods() -> list:
    """Loads Cleveland SPA neighborhood bounding boxes from the reference file."""
    if _NBHD_REF_PATH.exists():
        with open(_NBHD_REF_PATH, "r") as f:
            data = json.load(f)
            return data.get("neighborhoods", [])
    print(f"[WARN] Neighborhood reference not found: {_NBHD_REF_PATH}", file=sys.stderr)
    return []


def point_in_polygon(lat: float, lon: float, polygon: list) -> bool:
    """
    Ray-casting point-in-polygon test.
    polygon: list of [lon, lat] coordinate pairs (as returned from KML).
    """
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i][0], polygon[i][1]   # lon, lat
        xj, yj = polygon[j][0], polygon[j][1]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def find_neighborhood(lat: float, lon: float) -> Optional[dict]:
    """
    Finds the neighborhood whose polygon contains the point.
    If the neighborhood entry has 'polygons' (exact KML coords), uses point-in-polygon.
    Falls back to bounding box if no polygon data available.
    Returns the neighborhood dict or None.
    """
    neighborhoods = load_neighborhoods()
    for nbhd in neighborhoods:
        polygons = nbhd.get("polygons", [])
        if polygons:
            # Use exact polygon — consider a match if ANY polygon contains the point
            for poly in polygons:
                coords = poly.get("coordinates", [])
                if coords and point_in_polygon(lat, lon, coords):
                    return nbhd
        else:
            # Fallback: bounding box only
            bbox = nbhd.get("bbox", {})
            if (bbox.get("min_lat", 999) <= lat <= bbox.get("max_lat", -999) and
                    bbox.get("min_lon", 999) <= lon <= bbox.get("max_lon", -999)):
                return nbhd
    return None


def is_in_neighborhood(lat: float, lon: float, nbhd: dict) -> bool:
    """
    Returns True if (lat, lon) is within any polygon of the given neighborhood.
    Falls back to bounding box if no polygon data.
    """
    polygons = nbhd.get("polygons", [])
    if polygons:
        return any(
            point_in_polygon(lat, lon, poly.get("coordinates", []))
            for poly in polygons
        )
    bbox = nbhd.get("bbox", {})
    return (
        bbox.get("min_lat", 999) <= lat <= bbox.get("max_lat", -999) and
        bbox.get("min_lon", 999) <= lon <= bbox.get("max_lon", -999)
    )


def get_neighborhood_viewport(nbhd: dict) -> Optional[str]:
    """
    Returns the Redfin viewport string for a neighborhood bounding box.
    Format: 'min_lat,max_lat,min_lon,max_lon'
    """
    bbox = nbhd.get("bbox", {})
    if not bbox:
        return None
    return f"{bbox['min_lat']},{bbox['max_lat']},{bbox['min_lon']},{bbox['max_lon']}"


# ---------------------------------------------------------------------------
# Redfin zip → region_id lookup
# ---------------------------------------------------------------------------
# Redfin uses internal auto-increment IDs for zip code regions that don't
# correspond to the zip number. These were determined by inspecting Redfin
# network requests in the browser. Add more as needed.
OHIO_ZIP_REGION_IDS = {
    # Cleveland city zips
    "44102": 18512,
    "44103": 18513,
    "44104": 18514,
    "44105": 18515,
    "44106": 18516,
    "44107": 18517,
    "44108": 18499,  # Glenville/E 120th area — verified via browser network intercept
    "44109": 18519,  # NOTE: may need to verify per zip
    "44110": 18520,
    "44111": 18521,
    "44113": 18523,
    "44114": 18524,
    "44115": 18525,
    "44119": 18527,
    "44120": 18528,
    "44121": 18529,
    "44122": 18530,
    "44125": 18531,
    "44127": 18533,
    "44128": 18519,  # confirmed via browser network inspection
    "44129": 18534,
    "44130": 18535,
    "44134": 18536,
    "44135": 18537,
    # Lakewood / west side
    "44107": 18517,
    # East side suburbs
    "44143": 18543,
    "44124": 18532,
    "44118": 18526,
    "44040": 18508,
    # Akron
    "44301": 18560,
    "44302": 18561,
    "44303": 18562,
    "44304": 18563,
    "44305": 18564,
    "44306": 18565,
    "44307": 18566,
    "44310": 18568,
    "44311": 18569,
    "44312": 18570,
    "44313": 18571,
    "44314": 18572,
    "44319": 18573,
    # Columbus
    "43201": 18450,
    "43202": 18451,
    "43203": 18452,
    "43204": 18453,
    "43205": 18454,
    "43206": 18455,
    "43207": 18456,
    "43209": 18458,
    "43210": 18459,
    "43213": 18460,
    "43214": 18461,
    "43215": 18462,
    "43219": 18463,
    "43220": 18464,
    "43221": 18465,
    "43224": 18466,
    "43227": 18467,
    "43229": 18468,
    "43232": 18469,
    # Dayton
    "45401": 18600,
    "45402": 18601,
    "45403": 18602,
    "45404": 18603,
    "45405": 18604,
    "45406": 18605,
    "45409": 18606,
    "45410": 18607,
    "45414": 18608,
    "45416": 18609,
    "45419": 18610,
    "45420": 18611,
}


def lookup_zip_region_id(zipcode: str) -> Optional[int]:
    """
    Looks up a Redfin zip-level region_id.
    1. Checks the pre-cached OHIO_ZIP_REGION_IDS dict first.
    2. Scrapes redfin.com/zipcode/{zip} and extracts the region_id from the
       embedded JSON or network requests if not cached.
    Returns None if not found (caller should fall back to city-level region).
    """
    # 1. Check cache first
    if zipcode in OHIO_ZIP_REGION_IDS:
        return OHIO_ZIP_REGION_IDS[zipcode]

    # 2. Try scraping the Redfin zipcode page for the region_id
    import re
    url = f"https://www.redfin.com/zipcode/{zipcode}"
    try:
        resp = requests.get(url, headers=REDFIN_HEADERS, timeout=10)
        resp.raise_for_status()
        # Search for regionId in embedded JS/JSON
        matches = re.findall(r'"regionId"\s*:\s*(\d+)', resp.text)
        if matches:
            region_id = int(matches[0])
            print(f"[INFO] Discovered region_id={region_id} for zip {zipcode}", file=sys.stderr)
            OHIO_ZIP_REGION_IDS[zipcode] = region_id  # cache it
            return region_id
    except Exception as e:
        print(f"[WARN] Could not look up region_id for zip {zipcode}: {e}", file=sys.stderr)
    return None


# ---------------------------------------------------------------------------
# Redfin GIS API — sold comps
# ---------------------------------------------------------------------------

def fetch_redfin_gis_csv(
    region_id: str,
    region_type: int,
    market: str,
    sold_within_days: int,
    num_beds: Optional[int] = None,
    min_sqft: Optional[int] = None,
    max_sqft: Optional[int] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius_miles: float = 1.0,
    max_homes: int = 350,
    neighborhood_viewport: Optional[str] = None,
) -> list:
    """
    Calls Redfin's internal GIS CSV API.

    Redfin parameters:
      status=9      = Sold
      sf=1,2,3,5,6,7 = All property types (SFR, condo, townhouse, co-op, etc.)
      uipt=1,...,8  = All listing types
      v=8           = API version
      al=1          = Require lat/lon in results

    Returns list of dicts (one per sold property).
    """
    params = {
        "al": 1,
        "market": market,
        "num_homes": max_homes,
        "ord": "redfin-recommended-asc",
        "page_number": 1,
        "sf": "1,2,3,5,6,7",
        "sold_within_days": sold_within_days,
        "status": 9,
        "uipt": "1,2,3,4,5,6,7,8",
        "v": 8,
        "region_id": region_id,
        "region_type": region_type,
    }

    # Bedroom filter — Redfin native support
    if num_beds is not None:
        params["num_beds"] = num_beds
        params["max_num_beds"] = num_beds  # exact match

    # Sqft filter — Redfin native support
    if min_sqft is not None:
        params["min_sqft"] = min_sqft
    if max_sqft is not None:
        params["max_sqft"] = max_sqft

    # Viewport: prefer explicit neighborhood bbox, else compute from lat/lon radius
    if neighborhood_viewport:
        # Format from our JSON: 'min_lat,max_lat,min_lon,max_lon'
        # Redfin expects colon-separated: 'minLat:maxLat:minLon:maxLon'
        parts = neighborhood_viewport.split(",")
        if len(parts) == 4:
            params["viewport"] = ":".join(parts)
    elif lat is not None and lon is not None:
        deg_lat = radius_miles / 69.0
        deg_lon = radius_miles / (69.0 * abs(math.cos(math.radians(lat))))
        params["viewport"] = (
            f"{lat - deg_lat:.6f}:{lat + deg_lat:.6f}:"
            f"{lon - deg_lon:.6f}:{lon + deg_lon:.6f}"
        )

    url = "https://www.redfin.com/stingray/api/gis-csv"
    print(f"[INFO] Calling Redfin GIS API → {url}", file=sys.stderr)
    print(f"[INFO] Params: region_id={region_id}, sold_within_days={sold_within_days}, beds={num_beds}, sqft={min_sqft}-{max_sqft}", file=sys.stderr)

    resp = requests.get(url, params=params, headers=REDFIN_HEADERS, timeout=30)

    if resp.status_code == 403:
        raise RuntimeError("Redfin blocked the request (403). Try again in a moment or add a VPN.")
    if resp.status_code == 401:
        raise RuntimeError("Redfin returned 401. Request headers may need updating.")
    resp.raise_for_status()

    # Redfin's CSV has a disclaimer line at top — skip it
    content = resp.text
    lines = content.splitlines()
    # Find the actual CSV header row (starts with "ADDRESS" or "SALE TYPE")
    start_line = 0
    for i, line in enumerate(lines):
        if line.startswith("ADDRESS") or line.startswith("SALE TYPE"):
            start_line = i
            break

    csv_content = "\n".join(lines[start_line:])
    reader = csv.DictReader(io.StringIO(csv_content))
    results = list(reader)
    print(f"[INFO] Redfin returned {len(results)} sold properties", file=sys.stderr)
    return results


def parse_redfin_csv_row(row: dict) -> dict:
    """
    Normalises a raw Redfin CSV row into our standard comp dict.
    Redfin CSV columns (may vary slightly by market):
    ADDRESS, CITY, STATE OR PROVINCE, ZIP OR POSTAL CODE, PRICE, BEDS, BATHS,
    LOCATION, SQUARE FEET, LOT SIZE, YEAR BUILT, DAYS ON MARKET, SOLD DATE, etc.
    """
    def to_float(val):
        try:
            return float(str(val).replace(",", "").replace("$", "").strip())
        except (ValueError, TypeError):
            return None

    def to_int(val):
        f = to_float(val)
        return int(f) if f is not None else None

    price = to_float(row.get("PRICE") or row.get("SOLD PRICE") or "")
    sqft  = to_float(row.get("SQUARE FEET") or "")
    beds  = to_float(row.get("BEDS") or "")
    baths = to_float(row.get("BATHS") or "")

    comp = {
        "address":        str(row.get("ADDRESS", "")).strip(),
        "city":           str(row.get("CITY", "")).strip(),
        "state":          str(row.get("STATE OR PROVINCE", "")).strip(),
        "zip":            str(row.get("ZIP OR POSTAL CODE", "")).strip(),
        "sale_price":     price,
        "beds":           beds,
        "baths":          baths,
        "sqft":           sqft,
        "lot_size_sqft":  to_float(row.get("LOT SIZE") or ""),
        "year_built":     to_int(row.get("YEAR BUILT") or ""),
        "sale_date":      str(row.get("SOLD DATE") or row.get("CLOSE DATE") or "").strip(),
        "days_on_market": to_int(row.get("DAYS ON MARKET") or ""),
        "property_type":  str(row.get("PROPERTY TYPE") or "").strip(),
        "listing_url":    str(row.get("URL (SEE http://www.redfin.com/buy-a-home/comparative-market-analysis FOR INFO ON PRICING)") or row.get("URL") or "").strip(),
        "off_market":     "MLS" not in str(row.get("SALE TYPE", "")).upper(),
        "price_per_sqft": None,
        # Lat/lon — needed for neighborhood polygon geo-filter
        "latitude":       to_float(row.get("LATITUDE") or ""),
        "longitude":      to_float(row.get("LONGITUDE") or ""),
    }

    if comp["sale_price"] and comp["sqft"] and comp["sqft"] > 0:
        comp["price_per_sqft"] = round(comp["sale_price"] / comp["sqft"], 2)

    return comp


# ---------------------------------------------------------------------------
# Subject property lookup — using Redfin's search API
# ---------------------------------------------------------------------------

def lookup_subject_property(address: str) -> dict:
    """
    Uses Redfin's autocomplete + property stingray API to get subject beds/sqft.
    Falls back to empty dict if unavailable.
    """
    # Step 1: autocomplete to find the Redfin property ID
    autocomplete_url = "https://www.redfin.com/stingray/do/location-autocomplete"
    params = {"location": address, "v": 2, "count": 4}
    try:
        resp = requests.get(autocomplete_url, params=params, headers=REDFIN_HEADERS, timeout=10)
        resp.raise_for_status()
        # Response starts with "{}&&" — strip it
        text = resp.text.lstrip("{}&&").strip()
        data = json.loads(text)
        # Find the first "exactMatch" or "listing" type result
        items = data.get("payload", {}).get("sections", [{}])[0].get("rows", [])
        if not items:
            return {}
        match = items[0]
        url_path = match.get("url", "")
        print(f"[INFO] Subject property found: {match.get('name', '')} → {url_path}", file=sys.stderr)

        # Step 2: fetch property details
        detail_url = f"https://www.redfin.com/stingray/api/home/details/aboveTheFold"
        path_params = {"path": url_path, "accessLevel": 1}
        resp2 = requests.get(detail_url, params=path_params, headers=REDFIN_HEADERS, timeout=10)
        resp2.raise_for_status()
        text2 = resp2.text.lstrip("{}&&").strip()
        detail = json.loads(text2)
        payload = detail.get("payload", {})
        info = payload.get("mainHouseInfo", {}).get("propertyDetails", {}) or {}

        beds = info.get("beds") or info.get("numBeds")
        sqft = info.get("sqFt") or info.get("sqft") or info.get("totalSqFt")
        if beds or sqft:
            print(f"[INFO] Subject: {beds} beds, {sqft} sqft", file=sys.stderr)
            return {"beds": beds, "sqft": sqft, "url": url_path}
    except Exception as e:
        print(f"[WARN] Subject property lookup failed: {e}", file=sys.stderr)
    return {}


# ---------------------------------------------------------------------------
# Filter + sort comps
# ---------------------------------------------------------------------------

def filter_comps(
    comps: list,
    subject_city: str = "",
    subject_state: str = "",
    subject_beds: Optional[int] = None,
    subject_sqft: Optional[float] = None,
    sqft_tolerance: int = 300,
    neighborhood: Optional[dict] = None,
    property_type: str = "any",       # sfr | multi-family | condo | any
) -> list:
    """
    Applies post-fetch filters on top of Redfin's native API filters.
    Also deduplicates and removes records with no price/sqft.
    If 'neighborhood' is provided and has polygon data, drops comps outside the polygon.
    If 'property_type' is not 'any', only includes comps of that type.
    """
    city_lower  = subject_city.strip().lower()
    state_upper = subject_state.strip().upper()
    seen = set()
    out = []

    for c in comps:
        # Skip blank/incomplete rows
        if not c.get("sale_price") or c["sale_price"] <= 0:
            continue
        if not c.get("sqft") or c["sqft"] <= 0:
            continue

        # Dedup by address
        addr_key = str(c.get("address", "")).strip().lower()
        if addr_key in seen:
            continue
        seen.add(addr_key)

        # State guard (catches stale data)
        comp_state = str(c.get("state", "")).strip().upper()
        if comp_state and state_upper and comp_state != state_upper:
            print(f"[FILTER] Dropping {c['address']} ({comp_state}) — wrong state", file=sys.stderr)
            continue

        # Neighborhood polygon filter — uses exact KML boundary when available
        if neighborhood:
            comp_lat = c.get("latitude")
            comp_lon = c.get("longitude")
            if comp_lat is not None and comp_lon is not None:
                try:
                    comp_lat, comp_lon = float(comp_lat), float(comp_lon)
                    if not is_in_neighborhood(comp_lat, comp_lon, neighborhood):
                        print(f"[FILTER] Dropping {c['address']} — outside {neighborhood['name']} boundary", file=sys.stderr)
                        continue
                except (TypeError, ValueError):
                    pass  # No lat/lon — let it through (geocode unavailable)

        # Bedroom exact match (belt + suspenders over the API filter)
        if subject_beds is not None and c.get("beds") is not None:
            if int(c["beds"]) != int(subject_beds):
                print(f"[FILTER] Dropping {c['address']} — {c['beds']} beds (need {subject_beds})", file=sys.stderr)
                continue

        # Sqft tolerance
        if subject_sqft is not None and c.get("sqft") is not None:
            diff = abs(float(c["sqft"]) - float(subject_sqft))
            if diff > sqft_tolerance:
                print(f"[FILTER] Dropping {c['address']} — {c['sqft']} sqft (subj {subject_sqft}, diff {diff:.0f})", file=sys.stderr)
                continue

        # Property type filter
        if property_type != "any":
            comp_type = str(c.get("property_type", "")).lower()
            wanted_keywords = PROPERTY_TYPE_MAP.get(property_type, [])
            if not any(kw in comp_type for kw in wanted_keywords):
                print(f"[FILTER] Dropping {c['address']} — property type '{c.get('property_type')}' (want {property_type})", file=sys.stderr)
                continue

        out.append(c)

    # Sort newest first
    out.sort(key=lambda x: x.get("sale_date", "") or "", reverse=True)
    return out

# ---------------------------------------------------------------------------
# Property type mapping
# ---------------------------------------------------------------------------
# Maps our simple labels to Redfin PROPERTY TYPE column values (case-insensitive contains)
PROPERTY_TYPE_MAP: dict = {
    "sfr":          ["single family residential", "single-family", "detached"],
    "multi-family": ["multi-family", "multi family", "duplex", "triplex", "quadruplex",
                     "residential income", "2-4 unit", "5+ unit"],
    "condo":        ["condo", "co-op", "townhouse", "townhome"],
}


# ---------------------------------------------------------------------------
# Condition tier classification
# ---------------------------------------------------------------------------

def classify_condition(comps: list) -> list:
    """
    Assigns a condition_tier to each comp based on its $/sqft rank
    relative to the full pulled comp set.

    Tiers (by $/sqft quintile within the set):
      major-rehab     — bottom 20% (distressed, heavily discounted)
      minor-rehab     — 20–40%
      turnkey-low     — 40–60% (move-in ready but dated)
      turnkey-average — 60–80% (updated, clean)
      turnkey-high    — top 20% (fully renovated, top-of-market)

    If fewer than 5 comps, uses quartiles (4 tiers), still maps to the 5 labels.
    """
    valid = [c for c in comps if c.get("price_per_sqft") and c["price_per_sqft"] > 0]
    if not valid:
        for c in comps:
            c["condition_tier"] = "unknown"
            c["condition_label"] = "Unknown"
        return comps

    sorted_psf = sorted(c["price_per_sqft"] for c in valid)
    n = len(sorted_psf)

    def quintile_for(psf: float) -> int:
        """Returns 0-4 quintile index for a given $/sqft value."""
        for i, q in enumerate([0.20, 0.40, 0.60, 0.80]):
            if psf <= sorted_psf[max(0, int(n * q) - 1)]:
                return i
        return 4

    for c in comps:
        psf = c.get("price_per_sqft")
        if psf and psf > 0:
            tier_idx = quintile_for(float(psf))
            tier = CONDITION_TIERS[tier_idx]
        else:
            tier = "unknown"
        c["condition_tier"] = tier
        c["condition_label"] = CONDITION_LABELS.get(tier, "Unknown")

    return comps


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def fmt_price(val):
    if val is None: return "N/A"
    return f"${val:,.0f}"

def fmt_num(val, decimals=0):
    if val is None: return "N/A"
    return f"{val:,.{decimals}f}"


def print_markdown_table(comps: list, subject_address: str, subject_beds,
                         subject_sqft, sqft_tol, neighborhood: str = "",
                         condition: str = ""):
    cond_label = CONDITION_LABELS.get(condition, condition)
    print(f"\n## Comparable Sales — {subject_address}\n")
    print(f"*{date.today().isoformat()} · {len(comps)} comps · Source: Redfin (direct)*")
    if neighborhood:
        print(f"*Neighborhood: {neighborhood}*")
    filters = f"Filter: {subject_beds} beds, {subject_sqft} sqft ±{sqft_tol}"
    if condition:
        filters += f" · Condition: {cond_label}"
    print(f"*{filters}*\n")

    headers = ["Address", "Sale Price", "Beds", "Baths", "Sqft", "$/Sqft",
               "Yr Built", "Sale Date", "DOM", "Condition", "Off-Mkt"]
    widths  = [35, 12, 5, 6, 6, 8, 9, 13, 5, 22, 8]

    hdr = " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    sep = " | ".join("-" * widths[i] for i in range(len(headers)))
    print(f"| {hdr} |")
    print(f"| {sep} |")

    for c in comps:
        addr = f"{c.get('address','')}, {c.get('city','')}".strip(", ")
        row = [
            addr[:35],
            fmt_price(c.get("sale_price")),
            str(c.get("beds", "N/A")),
            str(c.get("baths", "N/A")),
            fmt_num(c.get("sqft")),
            fmt_price(c.get("price_per_sqft")),
            str(c.get("year_built", "N/A")),
            str(c.get("sale_date", "N/A")),
            str(c.get("days_on_market", "N/A")),
            str(c.get("condition_label", "N/A"))[:22],
            "Yes" if c.get("off_market") else "No",
        ]
        row_str = " | ".join(str(v).ljust(widths[i]) for i, v in enumerate(row))
        print(f"| {row_str} |")

    prices = [c["sale_price"] for c in comps if c.get("sale_price")]
    psf    = [c["price_per_sqft"] for c in comps if c.get("price_per_sqft")]
    if prices:
        sorted_p = sorted(prices)
        median = sorted_p[len(sorted_p) // 2]
        avg_psf = sum(psf) / len(psf) if psf else None
        print(f"\n**Summary**: {len(comps)} comps · Median: {fmt_price(median)} · "
              f"Avg $/sqft: {fmt_price(avg_psf)} · "
              f"Range: {fmt_price(sorted_p[0])} – {fmt_price(sorted_p[-1])}")



def save_csv(comps: list, path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fields = ["address","city","state","zip","sale_price","beds","baths","sqft",
              "price_per_sqft","lot_size_sqft","year_built","sale_date","days_on_market",
              "property_type","off_market","listing_url"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(comps)
    print(f"[INFO] CSV saved → {path}", file=sys.stderr)


def save_json(comps: list, subject: str, path: str, meta: dict):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    output = {
        "subject_address": subject,
        "pulled_at": date.today().isoformat(),
        "count": len(comps),
        "filters": meta,
        "comps": comps,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"[INFO] JSON saved → {path}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Fetch Redfin sold comps via direct API")
    parser.add_argument("--address",        required=True)
    parser.add_argument("--lookback-days",  type=int,   default=180)
    parser.add_argument("--radius-miles",   type=float, default=1.5,
                        help="Fallback radius if neighborhood bbox not found")
    parser.add_argument("--max-results",    type=int,   default=20)
    parser.add_argument("--sqft-tolerance", type=int,   default=300)
    parser.add_argument("--subject-beds",   type=int,   default=None)
    parser.add_argument("--subject-sqft",   type=float, default=None)
    parser.add_argument(
        "--condition",
        choices=CONDITION_TIERS + ["any"],
        default="any",
        help=(
            "Property condition to filter comps to. "
            "Options: major-rehab, minor-rehab, turnkey-low, turnkey-average, turnkey-high, any (default)"
        ),
    )
    parser.add_argument(
        "--property-type",
        choices=["sfr", "multi-family", "condo", "any"],
        default="sfr",
        help="Property type: sfr (default), multi-family, condo, or any",
    )
    parser.add_argument("--output",         default=None)
    args = parser.parse_args()

    slug = args.address.replace(" ", "_").replace(",", "").replace("/", "-")[:40]
    today = date.today().isoformat()
    json_path = args.output or f".tmp/comps_{slug}_{today}.json"
    csv_path  = json_path.replace(".json", ".csv")

    # 1. Geocode
    print(f"[INFO] Geocoding: {args.address}", file=sys.stderr)
    lat, lon, city, state, zipcode = geocode_address(args.address)
    print(f"[INFO] → lat={lat:.5f}, lon={lon:.5f}, city={city}, state={state}, zip={zipcode}", file=sys.stderr)

    # 2. Auto-detect subject specs
    subject_beds = args.subject_beds
    subject_sqft = args.subject_sqft
    if subject_beds is None or subject_sqft is None:
        subject_info = lookup_subject_property(args.address)
        if subject_beds is None:
            subject_beds = subject_info.get("beds")
            if subject_beds:
                subject_beds = int(subject_beds)
        if subject_sqft is None:
            raw_sqft = subject_info.get("sqft")
            if raw_sqft:
                subject_sqft = float(str(raw_sqft).replace(",", ""))

    if subject_beds is not None:
        print(f"[INFO] Filtering to: {subject_beds} beds, {subject_sqft} sqft ±{args.sqft_tolerance}", file=sys.stderr)
    else:
        print("[WARN] Could not detect subject beds/sqft — pass --subject-beds and --subject-sqft manually", file=sys.stderr)

    # Compute sqft bounds for the API (native filter)
    min_sqft = max_sqft = None
    if subject_sqft is not None:
        min_sqft = int(subject_sqft - args.sqft_tolerance)
        max_sqft = int(subject_sqft + args.sqft_tolerance)

    # 3. Neighborhood lookup — prioritize exact municipality over loose SPA bounding boxes
    if city.lower() == "east cleveland":
        nbhd = {
            "name": "East Cleveland",
            "investment_grade": "C-/F",  # Based on the user's map keys
            "boundary_notes": "East Cleveland City Limits",
            "bbox": {
                "min_lat": 41.515,
                "max_lat": 41.555,
                "min_lon": -81.605,
                "max_lon": -81.540
            }
        }
    else:
        nbhd = find_neighborhood(lat, lon)
        
    nbhd_name = nbhd["name"] if nbhd else ""
    nbhd_class = nbhd.get("investment_grade", "C") if nbhd else "C"
    nbhd_viewport = get_neighborhood_viewport(nbhd) if nbhd else None
    if nbhd:
        print(f"[INFO] Neighborhood: {nbhd_name} (Class {nbhd_class})", file=sys.stderr)
        if nbhd.get("boundary_notes"):
            print(f"[INFO] Bounds: {nbhd['boundary_notes']}", file=sys.stderr)
    else:
        print(f"[WARN] Address not matched to any Cleveland SPA neighborhood — using radius fallback", file=sys.stderr)

    # 4. Determine region — prefer zip-level (most precise), fall back to city
    zip_region_id = lookup_zip_region_id(zipcode) if zipcode else None
    if zip_region_id:
        region_id = str(zip_region_id)
        region_type = REGION_TYPE_ZIP
        city_key = city.strip().lower()
        market = REDFIN_CITY_MAP.get(city_key, (None, None, "cleveland"))[2]
        print(f"[INFO] Using zip region: {zipcode} (ID {region_id})", file=sys.stderr)
    elif city.strip().lower() in REDFIN_CITY_MAP:
        region_id, state_abbr, market = REDFIN_CITY_MAP[city.strip().lower()]
        region_type = REGION_TYPE_CITY
        print(f"[INFO] Using city region: {city} (ID {region_id})", file=sys.stderr)
    else:
        print(f"[WARN] Could not find region for city='{city}' zip='{zipcode}' — defaulting to Cleveland", file=sys.stderr)
        region_id = "10537"
        region_type = REGION_TYPE_CITY
        market = "cleveland"

    # 7. Pass neighborhood viewport to the API (overrides radius-based viewport)
    # We call fetch_redfin_gis_csv with viewport=nbhd_viewport if available
    # (the function already accepts lat/lon for radius-based fallback)
    time.sleep(0.5)
    raw_rows = fetch_redfin_gis_csv(
        region_id=region_id,
        region_type=region_type,
        market=market,
        sold_within_days=args.lookback_days,
        num_beds=subject_beds,
        min_sqft=min_sqft,
        max_sqft=max_sqft,
        # Use neighborhood bounding box if found, else radius viewport
        lat=lat if not nbhd_viewport else None,
        lon=lon if not nbhd_viewport else None,
        radius_miles=args.radius_miles,
        max_homes=350,
        neighborhood_viewport=nbhd_viewport,
    )

    # 8. Parse CSV rows → dicts
    comps_raw = [parse_redfin_csv_row(r) for r in raw_rows]

    # 9. Post-filter + sort (includes polygon geo-filter if neighborhood found)
    comps_all = filter_comps(
        comps_raw,
        subject_city=city,
        subject_state=state,
        subject_beds=subject_beds,
        subject_sqft=subject_sqft,
        sqft_tolerance=args.sqft_tolerance,
        neighborhood=nbhd,   # passes exact polygon — drops comps outside boundary
        property_type=args.property_type,
    )

    # 10. Classify condition (assigns condition_tier to every comp)
    comps_all = classify_condition(comps_all)

    # 11. Filter to requested condition tier
    if args.condition != "any":
        before = len(comps_all)
        comps_all = [c for c in comps_all if c.get("condition_tier") == args.condition]
        print(f"[INFO] Condition filter '{args.condition}': {before} → {len(comps_all)} comps", file=sys.stderr)

    comps = comps_all[:args.max_results]

    if not comps:
        print("[WARN] No comps found after filtering. Try:", file=sys.stderr)
        print("  --lookback-days 365   (extend time range)", file=sys.stderr)
        print("  --sqft-tolerance 500  (loosen sqft match)", file=sys.stderr)
        print("  --condition any       (remove condition filter)", file=sys.stderr)

    # 12. Output
    print_markdown_table(comps, args.address, subject_beds, subject_sqft,
                         args.sqft_tolerance, neighborhood=nbhd_name,
                         condition=args.condition if args.condition != "any" else "")
    save_csv(comps, csv_path)
    meta = {
        "subject_beds": subject_beds,
        "subject_sqft": subject_sqft,
        "sqft_tolerance": args.sqft_tolerance,
        "lookback_days": args.lookback_days,
        "neighborhood": nbhd_name,
        "neighborhood_class": nbhd_class,
        "condition": args.condition,
        "region_id": region_id,
        "region_type": region_type,
    }
    save_json(comps, args.address, json_path, meta)

    print(f"\n✅ Done. {len(comps)} comps found.", file=sys.stderr)
    if nbhd_name:
        print(f"   Neighborhood: {nbhd_name}", file=sys.stderr)
    if args.condition != "any":
        print(f"   Condition: {CONDITION_LABELS[args.condition]}", file=sys.stderr)
    print(f"   CSV  → {csv_path}", file=sys.stderr)
    print(f"   JSON → {json_path}", file=sys.stderr)


if __name__ == "__main__":
    main()

