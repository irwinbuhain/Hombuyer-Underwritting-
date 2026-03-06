#!/usr/bin/env python3
"""
export_to_sheets.py
-------------------
Exports Redfin comps JSON to a new Google Sheets spreadsheet.

Usage:
    python3 export_to_sheets.py <comps.json> [--title "Sheet Title"]

Requirements:
    pip install gspread google-auth
    credentials.json must exist in project root (Google Service Account or OAuth)

The script:
    1. Reads the comps JSON (output of fetch_redfin_comps.py)
    2. Filters to comps that have a redfin_url (have photos)
    3. Creates a new Google Sheet with formatted headers
    4. Writes all comp data + clickable Redfin hyperlinks
"""

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import gspread
    from google.oauth2.service_account import Credentials
    from google.oauth2.credentials import Credentials as OAuthCredentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    import pickle
except ImportError:
    print("Missing dependencies. Run: pip install gspread google-auth google-auth-oauthlib")
    sys.exit(1)

# ── Config ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
CREDS_FILE    = ROOT / "credentials.json"
TOKEN_FILE    = ROOT / "token.json"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADERS = [
    "Address", "City", "State", "Zip",
    "Sale Price", "Beds", "Baths", "Sqft", "$/Sqft",
    "Yr Built", "Sale Date", "DOM",
    "Property Type", "Off-Market", "Condition",
    "Neighborhood", "Redfin Link",
]

# ── Auth ─────────────────────────────────────────────────────────────────────
def get_gspread_client():
    """
    Returns an authenticated gspread client.
    Tries service account first, falls back to OAuth.
    """
    if CREDS_FILE.exists():
        creds_data = json.loads(CREDS_FILE.read_text())
        # Service account JSON has 'type': 'service_account'
        if creds_data.get("type") == "service_account":
            creds = Credentials.from_service_account_file(str(CREDS_FILE), scopes=SCOPES)
            return gspread.authorize(creds)

    # OAuth flow
    creds = None
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    return gspread.authorize(creds)


# ── Formatting ────────────────────────────────────────────────────────────────
def fmt_currency(val):
    if val is None: return ""
    try: return f"${int(float(val)):,}"
    except: return str(val)

def fmt_num(val, decimals=0):
    if val is None: return ""
    try:
        f = float(val)
        return f"{f:,.{decimals}f}" if decimals else f"{int(f):,}"
    except: return str(val)

def fmt_bool(val):
    return "Yes" if val else "No"


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Export comps to Google Sheets")
    parser.add_argument("json_file", help="Path to comps JSON file")
    parser.add_argument("--title", default=None, help="Sheet title (default: auto-generated)")
    parser.add_argument("--redfin-urls", default=None,
                        help="Path to JSON file mapping address→{url, has_photos}")
    args = parser.parse_args()

    # Load comps
    with open(args.json_file) as f:
        data = json.load(f)

    comps = data.get("comps", [])
    subject_address = data.get("subject_address", "Unknown Address")
    neighborhood = data.get("neighborhood", "")
    condition = data.get("condition_filter", "")

    if not comps:
        print("No comps found in JSON file.")
        sys.exit(1)

    # Load Redfin URL lookup if provided
    url_map = {}
    if args.redfin_urls and Path(args.redfin_urls).exists():
        with open(args.redfin_urls) as f:
            url_map = json.load(f)

    # Filter to comps with a Redfin URL (has photos)
    comps_with_photos = []
    for c in comps:
        addr_key = c.get("address", "").strip()
        url_info = url_map.get(addr_key, {})
        redfin_url = url_info.get("url", c.get("listing_url", ""))
        has_photos = url_info.get("has_photos", True)  # default include if no info

        if redfin_url and has_photos:
            c["redfin_url"] = redfin_url
            comps_with_photos.append(c)
        elif not url_map:
            # No URL map provided — include all comps with their listing_url
            c["redfin_url"] = c.get("listing_url", "")
            comps_with_photos.append(c)

    if not comps_with_photos:
        print("No comps with photos found. Check your --redfin-urls file.")
        # Fall back to all comps
        comps_with_photos = comps
        for c in comps_with_photos:
            c["redfin_url"] = c.get("listing_url", "")

    print(f"Exporting {len(comps_with_photos)} comps (photos only) to Google Sheets...")

    # Build rows
    rows = []
    for c in comps_with_photos:
        redfin_url = c.get("redfin_url", "")
        link_formula = f'=HYPERLINK("{redfin_url}","View on Redfin")' if redfin_url else ""
        rows.append([
            c.get("address", ""),
            c.get("city", ""),
            c.get("state", ""),
            c.get("zip", ""),
            fmt_currency(c.get("sale_price")),
            fmt_num(c.get("beds")),
            fmt_num(c.get("baths"), 1),
            fmt_num(c.get("sqft")),
            fmt_currency(c.get("price_per_sqft")),
            fmt_num(c.get("year_built")),
            c.get("sale_date", ""),
            fmt_num(c.get("days_on_market")),
            c.get("property_type", ""),
            fmt_bool(c.get("off_market")),
            c.get("condition_label", ""),
            neighborhood,
            link_formula,
        ])

    # Connect to Google Sheets
    client = get_gspread_client()

    # Create spreadsheet
    title = args.title or f"Comps — {subject_address}"
    spreadsheet = client.create(title)
    ws = spreadsheet.sheet1
    ws.update_title("Comps")

    # Write title row
    subtitle = f"Subject: {subject_address}  |  Neighborhood: {neighborhood}  |  Condition: {condition}  |  {len(comps_with_photos)} comps (with photos)"
    ws.update("A1", [[subtitle]])
    ws.merge_cells("A1:Q1")

    # Write headers row 2
    ws.update("A2", [HEADERS])

    # Write data rows start at row 3
    if rows:
        ws.update(f"A3", rows, value_input_option="USER_ENTERED")

    # Format header row bold
    ws.format("A2:Q2", {
        "textFormat": {"bold": True},
        "backgroundColor": {"red": 0.2, "green": 0.2, "blue": 0.2},
        "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
    })

    # Format title row
    ws.format("A1:Q1", {
        "textFormat": {"bold": True, "fontSize": 11},
        "backgroundColor": {"red": 0.13, "green": 0.53, "blue": 0.93},
        "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
        "horizontalAlignment": "CENTER",
    })

    # Share publicly (view only) so user can open it
    spreadsheet.share(None, perm_type="anyone", role="reader")

    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet.id}"
    print(f"\n✅ Google Sheet created!")
    print(f"   Title : {title}")
    print(f"   Comps : {len(comps_with_photos)}")
    print(f"   URL   : {url}")
    return url


if __name__ == "__main__":
    main()
