---
name: redfin-comps
description: Pulls comparable sold properties (comps) from Redfin for a given property address to support real estate underwriting. Use this skill whenever the user mentions comps, comparables, CMA, comparable market analysis, underwriting a property, finding what similar homes sold for, recently sold homes near an address, or wants to benchmark a property's value against the market. Trigger even if the user doesn't say "Redfin" explicitly — any request to find sold comps near a subject property should invoke this skill.
---

# Redfin Comps Skill

Fetches comparable sold properties from Redfin for a subject property address using the FireCrawl API, then formats results into a comps table suitable for real estate underwriting.

## Workflow

1. **Get the subject address** from the user (street, city, state, zip)
2. **Identify the market** — determine which metro (Cleveland, Columbus, Dayton, Akron) the address belongs to
3. **Run the script** — call `scripts/fetch_redfin_comps.py` with the address and desired parameters
4. **Present comps** — display the Markdown table and tell the user where the CSV lives in `.tmp/`

---

## Running the Script

```bash
cd /Users/irwinbuhain/Desktop/HomeBuyer+

python redfin-comps/scripts/fetch_redfin_comps.py \
  --address "1234 Example Ave, Cleveland, OH 44110" \
  --lookback-days 180 \
  --radius-miles 1.0 \
  --output .tmp/comps_output.json
```

### Key parameters

| Flag | Default | Description |
|---|---|---|
| `--address` | required | Full subject property address |
| `--lookback-days` | `180` | How far back to search for sold comps |
| `--radius-miles` | `1.0` | Search radius around subject address |
| `--max-results` | `20` | Cap on number of comps returned |
| `--output` | `.tmp/comps_<date>.json` | Where to save JSON output |

---

## Output

The script produces:
1. **A Markdown table** printed to stdout — ready to paste into notes or a deal sheet
2. **A CSV file** at `.tmp/comps_<slug>_<date>.csv`
3. **A JSON file** at the `--output` path for downstream use

### Comps table columns

| Column | Description |
|---|---|
| Address | Sold property street address |
| Sale Price | Final sold price |
| Beds | Number of bedrooms |
| Baths | Number of bathrooms |
| Sqft | Living area in sq ft |
| Price/Sqft | Sale price ÷ sqft |
| Lot Size | Lot in sq ft or acres |
| Year Built | Year of construction |
| Sale Date | Date of sale |
| Days on Market | Time from list to close |
| Property Type | SFR, Duplex, Condo, etc. |
| Source | "Redfin" |

---

## Neighborhood Context

See `references/neighborhoods.md` for the full graded neighborhood list for Cleveland, Columbus, Dayton, and Akron. When presenting comps, look up the subject's neighborhood grade and mention it — it helps the user understand whether they're buying in an A/B/C/D area.

---

## Limitations

- **Off-market sales**: Redfin aggregates some off-market (cash/non-MLS) data, but coverage is incomplete. The script pulls everything Redfin exposes; true wholesale/off-MLS comps may not appear.
- **Redfin coverage**: Redfin has strong MLS coverage in all four Ohio metros but may miss some niche rural sales.
- **FireCrawl credits**: JSON extraction format costs 5 credits per scrape page (1 base + 4 for JSON mode). The fallback route uses 2 scrapes (10 credits total).
- **Rate limits**: The script adds a 2-second wait between requests. Don't run in tight loops.
- **FireCrawl cache**: City-level viewport-filtered URLs can sometimes return stale cached data from other markets. The ZIP-level fallback URL (`/zipcode/{zip}/{STATE}/recently-sold/filter/...`) is more reliable and is tried automatically when city-level scrape returns nothing.

---

## Troubleshooting

- **0 comps or wrong-city results**: The script automatically falls back to ZIP-level multi-page search (up to 3 pages). If still 0, try widening `--radius-miles` or `--lookback-days`
- **Subject sqft auto-detection varies**: Redfin can report different sqft on different listing pages (e.g. 1,200 vs 1,500 for the same property). If you know the exact sqft, pass `--subject-sqft 1200` to override auto-detection.
- **FireCrawl error 401**: Check `FIRECRAWL_API_KEY` in `.env`
- **Address not geocoded**: Ensure the address includes city, state, and zip
- **Verify the Redfin URL**: The `[INFO] Redfin URL:` and `[INFO] ZIP URL:` log lines show exactly what was scraped — paste into your browser to spot-check

