# Seed Report — Task 1.3 (Grand Rapids restaurants)

_Generated 2026-04-17 23:02 UTC · Updated 2026-04-17 after Nearby-Search fix_

## 1. Totals

| Metric | Value |
| --- | ---: |
| Total restaurants | **1125** |
| From Google Places | 984 |
| From OpenStreetMap (OSM) | 141 |
| With website | 942 |
| With phone | 981 |
| With opening hours | 1125 |
| With Google rating | 973 |

Target was 1500–2500. Actual **1125** after both text-search and nearby-grid
runs. Falls short of the lower target because the 20 grid points returned
only 125 *new* places — the rest (~275) were duplicates of what the 45
text-search queries already captured. This is expected when a small urban
area gets saturated by category × region queries.

## 2. Top 15 Categories

| # | Category | Count |
| --: | --- | ---: |
| 1 | (null) | 84 |
| 2 | mexican_restaurant | 80 |
| 3 | coffee_shop | 78 |
| 4 | pizza_restaurant | 78 |
| 5 | bakery | 57 |
| 6 | fast_food_restaurant | 52 |
| 7 | sandwich_shop | 43 |
| 8 | chinese_restaurant | 41 |
| 9 | american_restaurant | 27 |
| 10 | breakfast_restaurant | 26 |
| 11 | chicken_restaurant | 24 |
| 12 | hamburger_restaurant | 22 |
| 13 | cafe | 22 |
| 14 | italian_restaurant | 19 |
| 15 | pizza | 19 |

**Note on `(null)` (84 rows):** these are mostly OSM rows without a
`cuisine` tag, or Places rows whose only `types` entries were the generic
`restaurant / food / point_of_interest / establishment` we filter out.
Acceptable for the hackathon — Task 1.4 will infer cuisine from menu.

## 3. Region Distribution

Each restaurant assigned to its nearest region center (PostGIS `ST_DistanceSphere`).

| Region | Center (lat, lng) | Count | Share |
| --- | --- | ---: | ---: |
| Grand Rapids | 42.9634, -85.6681 | 529 | 47.0% |
| Kentwood | 42.8687, -85.6447 | 346 | 30.8% |
| Wyoming MI | 42.9133, -85.7053 | 250 | 22.2% |

## 4. Bounding Box

- **lat:** `[42.80801, 43.11941]`
- **lng:** `[-85.87068, -85.33880]`

Distance-from-GR-center percentiles (miles): p50 ≈ 4.6mi · p90 ≈ 7.8mi · p95 ≈ 8.5mi.
Every row is within 25mi of the GR center (outlier cleanup applied — see §5).

## 5. Outliers (> 20mi from GR center) — ~~3 rows~~ _(deleted)_

| Name | Distance (mi) | Category | Source | Lat | Lng |
| --- | ---: | --- | --- | ---: | ---: |
| Buffalo Indian Restaurant | 1025.1 | indian_restaurant | places | 41.2994 | -105.5954 |
| Burger Mix and pizza | 134.6 | hamburger_restaurant | places | 42.3432 | -83.1576 |
| Deli Plaza Delicatessen | 132.6 | deli | places | 42.4261 | -83.1611 |

**Cause:** Places Text Search for `"<category> in Wyoming MI"` sometimes
matched the *state* of Wyoming. Two Detroit-area rows were probably
`"<category> in Grand Rapids MI"` accidentally matching the greater
Michigan area.

**Cleanup applied:**
```sql
DELETE FROM restaurants
WHERE ST_DistanceSphere(ST_MakePoint(lng,lat), ST_MakePoint(-85.6681, 42.9634))
      > 25 * 1609.34;
-- 3 rows removed (commit 587aae7)
```

The grid-only re-run added no new outliers.

## 6. Nearby-Search 400 Error — **fixed**

All 20 grid points of `places:searchNearby` returned `400 Bad Request` on the
first pass. Root cause confirmed via direct request with response body logged:

> `Invalid field: places.id,places.displayName,...,nextPageToken`

`searchNearby` does not accept `nextPageToken` in the `X-Goog-FieldMask` header
(unlike `searchText`). It also does not support pagination at all — max 20
results per call.

**Fix:** split the field mask per endpoint; drop the nearby pagination loop.

```python
_PLACE_FIELDS = ["places.id", "places.displayName", ...]
FIELD_MASK_TEXT   = ",".join([*_PLACE_FIELDS, "nextPageToken"])
FIELD_MASK_NEARBY = ",".join(_PLACE_FIELDS)
```

Grid re-run: 20 calls, 0 errors, **125 new places** inserted (the rest were
already captured by text search).

## 7. API Cost

| Stage | Calls | Cost |
| --- | ---: | ---: |
| Text Search (first run) | 114 | $3.65 |
| Nearby Search (first run, 400'd) | 0 billable | $0.00 |
| Nearby Search (re-run, 200 OK) | 20 | $0.64 |
| OSM Overpass | 1 | free |
| **Total** | **134** | **$4.29** |

Well inside the $200 monthly Places API free credit.

## 8. Next-Step Candidates (Task 1.4 preview)

- **942** restaurants have a website → crawler + Gemini parse candidates.
- That's 83.7% of the full set — very strong yield.
- OSM-sourced rows (141) typically lack website/phone/rating/hours — they
  may need a manual / Places-details second pass before being crawlable,
  or we simply skip them in Task 1.4 and come back later.
