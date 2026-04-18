# Backend Integration Reference (Phase 1 Complete)

All 10 HTTP endpoints are live on `http://<host>:8000`. Android emulator
uses `http://10.0.2.2:8000` to reach the host loopback.

## Conventions

- **Auth**: every endpoint except `/health`, `/restaurants/*`, and
  `/recommend` requires `X-Device-Id: <string>`. The string is an opaque
  per-install identifier (we use a UUID). Missing header → `401
  DEVICE_ID_REQUIRED`.
- **Content type** for POST bodies: `application/json` unless noted
  (only `/parse-menu-image` is multipart).
- **Error envelope** for all 4xx:
  ```json
  {"detail":{"error":{"code":"SOME_CODE","message":"...","details":{}}}}
  ```
- **Rate limits**: `/parse-menu-image` 5/min per device; `/reports`
  10/day per device. Both return `429 RATE_LIMITED` when exceeded.
- **CORS**: driven by `CORS_ORIGINS` env var (comma-separated). Defaults
  to `*` for dev.

## Points & levels (reference)

| Level | Points range | Name | Weight | Can rate? |
|---|---|---|---|---|
| 1 | 0–49 | Newbie | 1 | no |
| 2 | 50–149 | Scout | 1 | no |
| 3 | 150–399 | Regular | 1 | yes |
| 4 | 400–999 | Explorer | 2 | yes |
| 5 | 1000–2499 | Expert | 3 | yes |
| 7 | 2500–9999 | Veteran | 5 | yes |
| 10 | 10000+ | Legend | 10 | yes |

Point awards: submission +10 (+5 bonus on first for a restaurant),
confirmation +3, rating +2, daily login +1.

---

## 1. `GET /health`

Liveness probe. No auth.

```bash
curl http://10.0.2.2:8000/health
# → {"status":"ok","env":"local","db":true,"postgis_enabled":true}
```

---

## 2. `GET /me`

Device profile + daily-bonus check. Auto-creates the device on first call.

```bash
curl -H "X-Device-Id: $DEVICE_ID" http://10.0.2.2:8000/me
```

Response:
```json
{
  "device_id": "…",
  "display_name": null,
  "points": 1,
  "level": 1,
  "level_name": "Newbie",
  "level_weight": 1,
  "next_level_points": 50,
  "submission_count": 0,
  "confirmation_count": 0,
  "daily_streak": 1,
  "can_rate_restaurants": false,
  "first_seen": "2026-04-18T01:41:33.146293Z"
}
```

Android notes:
- Safe to call at app launch; `last_daily_bonus` is keyed in PT so you
  don't need to pass a timezone.
- `next_level_points` returns `-1` at Legend (hide "next level" UI).
- `can_rate_restaurants` is the flag to gate the rating button.

---

## 3. `GET /restaurants/nearby`

Map pins within `radius_m` of `(lat,lng)`. No auth.

```bash
curl "http://10.0.2.2:8000/restaurants/nearby?lat=42.9634&lng=-85.6681&radius_m=2000&limit=100"
```

Query params:
- `lat`, `lng` *(required)*
- `radius_m` (default 2000, max 50000)
- `tier` (`survive` | `cost_effective` | `luxury`)
- `verified_only` (bool)
- `include_empty` (bool, default true — set false to hide pins with no menu yet)
- `limit` (default 100, max 500)

Each restaurant carries a `menu_status`:
- `populated_verified` — green pin (has a human-verified cheapest item)
- `populated_ai` — yellow pin (Gemini-parsed, awaiting confirmations)
- `empty` — grey pin (no menu rows yet — good submission target)

`cheapest_menu` is `null` when `menu_status == "empty"`.

Results are sorted by `status_rank` (verified first), then distance.

---

## 4. `GET /restaurants/{id}`

Full detail + menu grouped by tier.

```bash
curl http://10.0.2.2:8000/restaurants/7858d9b7-4240-4258-8db6-81b2c62cf6e5
```

Response (abridged):
```json
{
  "id": "…",
  "name": "Two Beards Deli",
  "address": "…",
  "phone": "…",
  "website": "…",
  "lat": 42.96,
  "lng": -85.67,
  "google_rating": 4.7,
  "app_rating": 4.0,
  "rating_count": 3,
  "hours": {"openNow": true, "periods": [...]},
  "menu": {
    "survive":        [{"id":"…","name":"Pickle Spear","price_cents":50, ...}],
    "cost_effective": [...],
    "luxury":         [...]
  }
}
```

`hours` is the raw Google Places `hours_json` — periods are 0=Sun..6=Sat.

Unknown `id` → `404 RESTAURANT_NOT_FOUND`.

---

## 5. `POST /submissions`

User-submitted menu item (after photo parse or manual entry).

```bash
curl -X POST http://10.0.2.2:8000/submissions \
  -H "X-Device-Id: $DEV" -H "Content-Type: application/json" \
  -d '{
    "restaurant_id": "…",
    "menu_name": "Falafel wrap",
    "price_cents": 699,
    "photo_url": null,
    "gemini_parsed": null,
    "source": "gemini_photo"
  }'
```

- `source` must be one of `gemini_photo`, `user_manual`, `web_crawl`.
- Fuzzy-matches to an existing active menu_item by normalized name.
  - Price within ±$1 → logs a confirmation on that row.
  - Price off by $1–$3 → marks both disputed.
  - Larger gap (or no match) → creates a new `ai_parsed` menu_item.
- Returns `is_first_submission: true` + `+5` bonus + `bonus_message`
  when the restaurant had no menu rows before.
- `level_up: true` when this submission crossed a level threshold.

---

## 6. `POST /confirmations`

"Is this price still right?" feedback.

```bash
curl -X POST http://10.0.2.2:8000/confirmations \
  -H "X-Device-Id: $DEV" -H "Content-Type: application/json" \
  -d '{
    "menu_item_id": "…",
    "is_agreement": true
  }'
```

- `is_agreement: false` + optional `reported_price` (cents, 1-1500). If
  `reported_price` is provided, a new `ai_parsed` menu_item with
  `source: "user_manual"` is created alongside the disputed original.
- **Do NOT send `reported_price` with `is_agreement: true`** → 422.
- Duplicate (same device + menu) → `409 ALREADY_CONFIRMED`.
- Response reflects the auto-verify trigger: once confirmation_weight
  hits 5, `verification_status` flips `ai_parsed → human_verified` in
  the same response.
- +3 points awarded.

---

## 7. `POST /ratings`

Restaurant star rating. **Requires level ≥ 3.**

```bash
curl -X POST http://10.0.2.2:8000/ratings \
  -H "X-Device-Id: $DEV" -H "Content-Type: application/json" \
  -d '{"restaurant_id":"…","score":4,"comment":"solid"}'
```

- `score`: 1–5 integer.
- Level < 3 → `403 INSUFFICIENT_LEVEL` (surface via `can_rate_restaurants`
  in `/me` before letting the user tap).
- Duplicate → `409 ALREADY_RATED` (we don't support update-in-place yet).
- `restaurant_updated.app_rating` is the weighted mean across all
  ratings: `SUM(score * weight_applied) / SUM(weight_applied)`.
- +2 points.

---

## 8. `POST /reports`

Flag a menu_item as wrong/spam.

```bash
curl -X POST http://10.0.2.2:8000/reports \
  -H "X-Device-Id: $DEV" -H "Content-Type: application/json" \
  -d '{"menu_item_id":"…","reason":"wrong_price","comment":"it's $12 not $6"}'
```

- `reason` enum: `wrong_price` | `not_on_menu` | `spam` | `inappropriate` | `other`.
- 3rd pending report on the same menu_item auto-flips it to
  `verification_status: disputed` via DB trigger. The response surfaces
  this as `menu_item_auto_disputed: true` — show a "reported, thanks"
  toast and optionally a "flagged as disputed" sub-line.
- Duplicate (same device + menu) → `409 ALREADY_REPORTED`.
- Rate limit: **10 reports/day per device** → `429 RATE_LIMITED`.
- Unknown menu_item → `404 MENU_ITEM_NOT_FOUND`.

---

## 9. `POST /parse-menu-image`  ⭐ demo-critical

Sends a photo to Gemini Vision, returns structured items.

```bash
curl -X POST http://10.0.2.2:8000/parse-menu-image \
  -H "X-Device-Id: $DEV" \
  -F "image=@menu.jpg"
```

**Important for Android:**
- **Multipart field name MUST be `image`** (lowercase, singular).
- Accepted MIME types: `image/jpeg`, `image/jpg`, `image/png`,
  `image/webp`. Other types → `400 UNSUPPORTED_MEDIA_TYPE`.
- Empty upload → `400 EMPTY_IMAGE`.
- Rate limit: **5 calls/min per device** → `429 RATE_LIMITED` (protects
  Gemini quota). Debounce the camera button accordingly.

Response:
```json
{
  "items": [
    {"name":"Hummus pita","description":"with tahini","price_cents":450,"category":"mediterranean","confidence":0.95},
    {"name":"Falafel wrap","description":null,"price_cents":699,"category":"mediterranean","confidence":0.88}
  ],
  "restaurant_name_detected": null,
  "warnings": []
}
```

- `warnings` can include: `"unreadable"` (blurry/low-quality),
  `"not_a_menu"` (wrong subject), `"parse_error"`/`"api_error"` (Gemini
  side issue), `"dropped_N_invalid_items"` (some items failed Pydantic
  validation, rest kept).
- **This endpoint does NOT persist anything.** After the user confirms
  the parsed items, POST them one-by-one to `/submissions` with
  `source: "gemini_photo"` (and optionally echo the original Gemini
  payload in `gemini_parsed` for audit).
- `items` may be empty on garbage input — show a friendly "couldn't
  read the menu" UI rather than treating it as an error.

---

## 10. `POST /recommend`

Natural-language recommendation over nearby menus.

```bash
curl -X POST http://10.0.2.2:8000/recommend \
  -H "Content-Type: application/json" \
  -d '{
    "lat": 42.9634,
    "lng": -85.6681,
    "query": "비 오는 날 따뜻한 거 $10 이하",
    "max_results": 5
  }'
```

- No `X-Device-Id` required.
- Search radius is 2 km, hard-coded. We hand Gemini the top 50
  candidates (verified-first, then by distance) and it picks up to
  `max_results`.
- `reason` is kept under 80 chars and written in the same language as
  `query` (Korean/English/etc.) — the prompt enforces this but Gemini
  can slip, so clip client-side if you need a hard cap.
- Empty geographic area → `recommendations: []` (Gemini is skipped to
  save quota).
- Gemini occasionally hallucinates a UUID; both the service layer and
  the router filter to the whitelist, so you'll only ever receive IDs
  that exist in the nearby set.

Response:
```json
{
  "recommendations": [
    {
      "restaurant_id": "…",
      "restaurant_name": "Two Beards Deli",
      "menu_item_id": "…",
      "menu_name": "The George Clooney (Half)",
      "price_cents": 1400,
      "distance_m": 176,
      "verification_status": "ai_parsed",
      "reason": "Cheapest sandwich nearby, likely can be served warm."
    }
  ]
}
```

---

## Known things the Android side should plan for

- `app_rating` can be `null` when a restaurant has zero ratings yet —
  UI should show "No ratings" not `0.0`.
- `cheapest_menu` is `null` when `menu_status == "empty"` — don't assume
  it's always present in the nearby pin payload.
- The `hours_json` schema matches Google Places' `regularOpeningHours`
  format. Android's existing Google Places parsing can reuse it.
- Error envelope always has `detail.error.code` — key off that, not the
  `message` (which may be i18n'd later).
- Timestamps are ISO-8601 UTC with `Z` suffix.
- Photo URLs in `photo_url` fields are DigitalOcean Spaces CDN links
  (public read). No signed-URL negotiation needed.

## Backend milestone

- 10 HTTP endpoints across 7 routers
- 68 pytest tests passing (unit + integration against real Postgres)
- PostGIS auto-detected at startup; bbox + Haversine fallback
- Gemini failures collapse to safe defaults, never 500 the request
- All curl smoke tests green on 2026-04-18
