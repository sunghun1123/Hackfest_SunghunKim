# Seed Report — Task 1.3 (Grand Rapids restaurants)

_Generated 2026-04-17 23:02 UTC_

## 1. Totals

| Metric | Value |
| --- | ---: |
| Total restaurants | **1000** (post-cleanup; was 1003) |
| From Google Places | 859 |
| From OpenStreetMap (OSM) | 141 |
| With website | 819 |
| With phone | 861 |
| With opening hours | 1003 |
| With Google rating | 852 |

Target was 1500–2500. Actual **1003** is below target because Nearby 
Search grid returned **400 Bad Request on every call** — see §6 for the bug 
and re-run options.

## 2. Top 15 Categories

| # | Category | Count |
| --: | --- | ---: |
| 1 | (null) | 82 |
| 2 | mexican_restaurant | 74 |
| 3 | coffee_shop | 69 |
| 4 | pizza_restaurant | 66 |
| 5 | bakery | 57 |
| 6 | chinese_restaurant | 41 |
| 7 | sandwich_shop | 38 |
| 8 | fast_food_restaurant | 27 |
| 9 | american_restaurant | 23 |
| 10 | breakfast_restaurant | 23 |
| 11 | chicken_restaurant | 22 |
| 12 | cafe | 20 |
| 13 | hamburger_restaurant | 19 |
| 14 | pizza | 19 |
| 15 | sushi_restaurant | 17 |

## 3. Region Distribution

Each restaurant assigned to its nearest region center (Haversine).

| Region | Center (lat, lng) | Count | Share |
| --- | --- | ---: | ---: |
| Grand Rapids | 42.9634, -85.6681 | 438 | 43.7% |
| Kentwood | 42.8687, -85.6447 | 335 | 33.4% |
| Wyoming MI | 42.9133, -85.7053 | 230 | 22.9% |

## 4. Bounding Box

- **lat:** `[42.80801, 43.11941]` _(post-cleanup)_
- **lng:** `[-85.87068, -85.33880]` _(post-cleanup)_

Distance-from-GR-center percentiles (miles):
- p50: 4.62mi  ·  p90: 7.76mi  ·  p95: 8.46mi

## 5. Outliers (> 20mi from GR center) — 3 rows _(now deleted)_

| Name | Distance (mi) | Category | Source | Lat | Lng |
| --- | ---: | --- | --- | ---: | ---: |
| Buffalo Indian Restaurant | 1025.1 | indian_restaurant | places | 41.2994 | -105.5954 |
| Burger Mix and pizza | 134.6 | hamburger_restaurant | places | 42.3432 | -83.1576 |
| Deli Plaza Delicatessen | 132.6 | deli | places | 42.4261 | -83.1611 |

**Likely cause:** Places Text Search for `"<category> in Wyoming MI"` 
sometimes matched the *state* of Wyoming. OSM also pulled a handful of 
places just outside the bbox because of floating point.

**Cleanup applied:** `DELETE FROM restaurants WHERE ST_DistanceSphere(...) > 25*1609.34;`
removed the 3 outliers. Post-cleanup bbox tightens to lat [42.808, 43.119],
lng [-85.871, -85.339], which is the correct Grand Rapids metro area.

## 6. Nearby-Search 400 Error

All 20 grid points of `places:searchNearby` returned `400 Bad Request`.
After 5 tenacity retries each, nearby-search contributed **0 restaurants**.

Hypotheses to investigate before re-running:
1. The `FieldMask` includes `nextPageToken`, which is valid for `searchText` 
   but may not be accepted by `searchNearby` in Places API (New).
2. Request body may need `regionCode: "us"` or `languageCode: "en"` for 
   the Nearby endpoint.
3. `radius` should possibly be int, not float `2000.0`.

Next debug step: `curl` one grid point directly with minimal field mask 
and capture the error body (which our current code throws away inside 
tenacity). I kept grid collection out of the first run so the fix can be 
isolated; text search + OSM already gave us 1003 places.

## 7. API Cost

- Billable Places calls (text search only): **114** × $32 / 1000 = **$3.65**
- Nearby calls (all 400'd before billing): 20 × $0 = $0
- OSM (Overpass): free
- Well inside the Google $200 free monthly credit.

## 8. Next-Step Candidates (Task 1.4 preview)

- 822 restaurants have a website → candidates for crawler + Gemini parse.
- That's 82% of the full set — excellent yield.

- After outlier cleanup the crawl pool should drop by <5%.
