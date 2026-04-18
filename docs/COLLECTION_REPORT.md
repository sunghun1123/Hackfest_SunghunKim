# Menu Collection Report

_Multi-pipeline menu data collection for Broken Lunch GR._
_Started 2026-04-17 · see individual pipeline sections for completion timestamps._

Pipelines run:

| # | Pipeline | Source label | Status |
| --- | --- | --- | --- |
| A | Website HTML + Gemini text | `gemini_web` | **complete** |
| B | Playwright screenshot + Gemini Vision | `gemini_screenshot` | pending |
| C | Places Photos Mining | `gemini_places_photo` | pending |
| D | PDF Menu Hunt | `gemini_pdf` | pending |
| E | Yelp Menu (optional) | `gemini_yelp` | pending |

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

_pending_

## Pipeline C — Places Photos Mining

_pending_

## Pipeline D — PDF Menu Hunt

_pending_

## Pipeline E — Yelp Menu

_pending — will execute only if legal-safe and robots.txt permits_

---

## Overall

_populated after all pipelines finish._

| Metric | Value |
| --- | ---: |
| Restaurants with ≥ 1 menu item | 184 / 1125 (16.4%) |
| Total menu items (all sources) | 8506 |
| Total Gemini spend | ~$1.43 |
