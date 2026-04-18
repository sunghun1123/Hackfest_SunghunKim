# Menu Collection Report

_Multi-pipeline menu data collection for Broken Lunch GR._
_Started 2026-04-17 · see individual pipeline sections for completion timestamps._

Pipelines run:

| # | Pipeline | Source label | Status |
| --- | --- | --- | --- |
| A | Website HTML + Gemini text | `gemini_web` | **complete** |
| B | Playwright screenshot + Gemini Vision | `gemini_screenshot` | **complete** |
| C | Places Photos Mining | `gemini_places_photo` | **complete** |
| D | PDF Menu Hunt | `gemini_pdf` | **complete** |
| E | Yelp Menu (optional) | `gemini_yelp` | **skipped** (robots.txt disallows) |

---

## Pipeline A — Website HTML + Gemini text

**Script:** [backend/scripts/02_crawl_and_parse.py](../backend/scripts/02_crawl_and_parse.py)
**Model:** `gemini-2.5-flash`
**Completed:** 2026-04-17, full run + retry-failed
**Runtime:** ~65 min on Tier 1 (after initial free-tier 429 storm)

### Target pool

| Metric | Value |
| --- | ---: |
| Total restaurants in DB | 1125 |
| Non-OSM with website (crawl pool) | 889 |
| OSM rows skipped | 141 (kept as empty pins for first-submission bonus) |

### Outcomes

| Status | Count | Share of pool |
| --- | ---: | ---: |
| **success** (menu extracted) | **184** | 20.7% |
| no_menu_found | 629 | 70.8% |
| robots_blocked | 57 | 6.4% |
| parse_failed (retryable) | 38 | 4.3% |
| http_error | 0 | 0% |
| _logged total_ | _908_ | _(some rows re-logged across runs)_ |

Note: 5 `parse_failed` rows in the final log are JSON/schema-parse edge cases; the rest are legitimate transient failures. Runnable again with `--retry-failed` after Pipelines B–E.

### Menu items saved

| Metric | Value |
| --- | ---: |
| Total `menu_items` rows (`source='gemini_web'`) | **8506** |
| Avg items per successful restaurant | 46.2 |
| Tier `survive` (≤ $5) | 1816 (21.3%) |
| Tier `cost_effective` ($5.01–10) | 2682 (31.5%) |
| Tier `luxury` ($10.01–15) | 4008 (47.1%) |

### Top 5 richest extractions

| Restaurant | Items |
| --- | ---: |
| Great Lakes Chinese Restaurant | 250 |
| First Wok Chinese Restaurant | 168 |
| Real Food Cafe | 164 |
| Toast'n Tea | 163 |
| 7 Monks Taproom Grand Rapids | 160 |

### API cost

| Metric | Value |
| --- | ---: |
| Gemini calls | 529 |
| Gemini errors | 5 |
| Script-estimated cost (~30k in / 1.5k out avg) | **~$1.43** |
| Budget consumed of $10 cap | ~14% |

### Known limitations

1. **Modern JS-SPA sites dominate no_menu rows.** Shell HTML contains nav/footer but no menu data; visible text has category names without prices. These are the primary targets for Pipeline B (Playwright + Vision).
2. **Fast-food chains (Chipotle, Subway, Chick-fil-A, Popeyes, Wendy's, Burger King, Arby's)** are all no_menu — their sites are heavily JS-rendered order flows. Pipeline B should recover most of these.
3. **Facebook-only restaurants (57 robots_blocked)** are unreachable without a logged-in session. Pipeline C (Places Photos) is the best backup for these — Google cached menu photos bypass the site entirely.
4. **OSM 141 skipped** — intentional; these become empty pins.

### Early 429 incident (resolved)

Initial run on Gemini free tier hit `20 RPM` cap → 31 of first 60 calls failed with 429. User upgraded to Tier 1 (prepaid $10); subsequent run had **0 rate-limit errors**. No data lost — failed rows re-processed in second pass.

---

## Pipeline B — Playwright screenshot + Gemini Vision

**Script:** [backend/scripts/03_screenshot_and_parse.py](../backend/scripts/03_screenshot_and_parse.py)
**Models:** Playwright headless Chromium + `gemini-2.5-flash` (vision)
**Completed:** 2026-04-17
**Runtime:** ~72 min, concurrency=2

### Target pool

Restaurants flagged `no_menu_found` by Pipeline A (JS-SPA sites, franchise locators, etc.) — the screenshot path bypasses the shell-HTML problem entirely.

| Metric | Value |
| --- | ---: |
| Targets (no_menu_found w/ website, non-OSM) | 629 |
| Success | **119** (18.9%) |
| No items extracted | 454 |
| Nav / screenshot failed | 55 |

### Menu items saved

| Metric | Value |
| --- | ---: |
| Rows (`source='gemini_screenshot'`) | **4015** |
| Avg per successful restaurant | 33.7 |
| survive / cost_effective / luxury | 1027 / 1332 / 1656 |

Top 5 by yield: **Jia Yuan (206), Beijing Kitchen (150), Golden Wok (127), Lindo Mexico (122), Morning Belle (118)** — exactly the JS-heavy sites Pipeline A couldn't read.

### Engineering notes

- Full-page screenshot with scroll-to-bottom + scroll-back, PIL-chunked when taller than 2000px (max 4 chunks / page).
- URL fallback chain: given URL → `/menu` → `/menus` → homepage.
- Per-worker `asyncio.wait_for(..., timeout=90s)` — prevented a single Popeyes store-locator page from hanging the pool.
- Two bugs fixed mid-run: Gemini occasionally returned a bare JSON array (coerced to `{items: [...]}`) and Pydantic forward-ref failed across dynamic imports (inlined the schema classes).

### API cost

| Metric | Value |
| --- | ---: |
| Gemini vision calls | 576 (errors 1) |
| Script-estimated cost | **~$1.56** |

---

## Pipeline C — Places Photos Mining

**Script:** [backend/scripts/04_places_photos.py](../backend/scripts/04_places_photos.py)
**Services:** Google Places API (New) + `gemini-2.5-flash` (vision, two-stage)
**Completed:** 2026-04-17
**Runtime:** ~78 min, concurrency=3

### Target pool

Restaurants with a Google `place_id` and **zero** existing menu items (i.e. the long-tail Pipelines A/B both missed).

| Metric | Value |
| --- | ---: |
| Targets | 766 |
| Success | **192** (25.1%) |
| No photos on listing | 11 |
| No menu-like photo found | 561 |
| HTTP / timeout errors | 2 |

### Flow

1. `GET /v1/places/{place_id}` with field mask `id,displayName,photos` — up to 10 photo refs.
2. Download first 4 via `/v1/{photo.name}/media?maxWidthPx=1600`.
3. **Stage 1** Gemini Vision: "is this a menu?" (yes/no).
4. **Stage 2** Gemini Vision on first menu-like photo: extract items + prices against strict schema.

### Menu items saved

| Metric | Value |
| --- | ---: |
| Rows (`source='gemini_places_photo'`) | **4722** |
| Avg per successful restaurant | 24.6 |
| survive / cost_effective / luxury | 1804 / 1993 / 925 |

Top 5 by yield: **BIGGBY COFFEE (261), Jimmy John's (228), Starbucks (144), FENG CHA (132), Arby's (126)** — recovered fast-food and coffee chains whose websites blocked everything else. Tier skew toward `survive` / `cost_effective` is the expected fast-food price distribution.

### API cost

| Metric | Value |
| --- | ---: |
| Places Details calls | 766 |
| Places Photo fetches | 2994 |
| Gemini calls (is_menu + parse) | 3259 (errors 0) |
| Script-estimated total cost | **~$31.31** |

Well within the $200 Places free tier. Dominant line-item is `Photo fetches × $0.007`.

---

## Pipeline D — PDF Menu Hunt

**Script:** [backend/scripts/05_pdf_hunter.py](../backend/scripts/05_pdf_hunter.py)
**Models:** `pypdfium2` (render) + `gemini-2.5-flash` (vision)
**Completed:** 2026-04-17
**Runtime:** ~20 min, concurrency=4

### Target pool

Restaurants with **zero** existing menu items after A/B/C — a last-chance sweep for places that publish PDF menus.

| Metric | Value |
| --- | ---: |
| Targets | 641 |
| PDFs discovered | 200 |
| Success | **17** (2.7%) |
| No PDF found | 453 |
| PDF parse failures | 171 |

### Flow

1. HEAD-probe ~17 common PDF paths (`/menu.pdf`, `/wp-content/uploads/menu.pdf`, `/our-menu.pdf`, etc.).
2. Fall back to scraping homepage + `/menu` for `<a href>` ending in `.pdf` with menu keywords.
3. Render first 6 pages with pypdfium2 at 1.4× scale, resize to ≤2000px wide, send to Gemini Vision.

### Outcome & limitations

Dry-run on first 30 by ID hit 6.7% (above the 5% launch threshold), but full-run dropped to **2.7%** — the broader pool is polluted with:

- Instagram / Facebook URLs returning HTML despite `.pdf` suffix (`pdf_fetch_fail`)
- Chain-corporate PDFs that aren't menus (Noodles & Co ACA 1095-C form, Pizza Hut nutrition sheets) → `pdf_no_items`
- WordPress sites with a PDF on the page that isn't *the* menu

Still net-positive: **476 new menu items** that none of A/B/C could reach, for ~$0.20 in Gemini cost.

Top 5 by yield: **Jose Babushka's (84), Big Bob's Pizza (75), Charlie's Bar & Grille (67), 333 Cafe (54), Kawa Sushi and Grill (45)** — independent sit-down restaurants with marketing-designer-produced PDF menus.

### API cost

| Metric | Value |
| --- | ---: |
| Gemini calls | 67 (errors 0) |
| Script-estimated cost | **~$0.20** |

---

## Pipeline E — Yelp Menu

**Skipped.** Yelp's [`/robots.txt`](https://www.yelp.com/robots.txt) sets `User-agent: *` → `Disallow: /` (full site exclusion). Per the plan's critical rule *"will execute only if legal-safe and robots.txt permits,"* this pipeline was not built. No code committed for it.

---

## Overall

| Metric | Value |
| --- | ---: |
| Restaurants with ≥ 1 menu item | **489 / 1125** (43.5%) |
| Total menu items (all sources) | **17,719** |
| Total pipelines shipped | 4 of 5 (E declined) |
| Total estimated spend | **~$34.50** (Gemini ~$3.20 + Places ~$31.31) |
| Gemini budget ($10) | ~32% consumed |
| Places free credit ($200) | ~16% consumed |

### Items by source

| Source | Items | Unique restaurants |
| --- | ---: | ---: |
| `gemini_web` (A) | 8506 | 184 |
| `gemini_places_photo` (C) | 4722 | 192 |
| `gemini_screenshot` (B) | 4015 | 119 |
| `gemini_pdf` (D) | 476 | 17 |
| **Total** | **17,719** | **489** (deduplicated) |

### Pipeline overlap

| Covered by | Restaurants |
| --- | ---: |
| 1 pipeline | 467 |
| 2 pipelines | 21 |
| 3 pipelines | 1 |

The four pipelines are almost entirely **orthogonal** — 95% of restaurants with data only got it from one pipeline. This validates the multi-pipeline decision: collapsing to any single source would have lost ~60% of the coverage.

### Tier distribution (all sources)

| Tier | Items | Share |
| --- | ---: | ---: |
| `survive` (≤ $5) | 4785 | 27.0% |
| `cost_effective` ($5.01–10) | 6176 | 34.9% |
| `luxury` ($10.01–15) | 6758 | 38.1% |

Plenty of density at all three price tiers for the Android app's ranking logic.

### Remaining 636 restaurants with no menu items

Mostly expected categories that no pipeline can crack cheaply:

- **OSM-only rows (141)** — kept as empty pins by design for first-submission bonus in the user flow.
- **Franchise sites** that render no prices anywhere on the public web (Chipotle, Subway, Chick-fil-A, specific Wendy's locations). Menus exist only behind logged-in ordering flows.
- **Facebook-only restaurants (57)** that Pipeline A hit as `robots_blocked` and that had no Places photos suitable for parsing.
- **Truly menu-less small businesses** — coffee carts, cake studios, catering-only operations.

Gaps here should be filled by the **user-contribution path** (crowd-sourced menu submissions) rather than more automated crawlers.
