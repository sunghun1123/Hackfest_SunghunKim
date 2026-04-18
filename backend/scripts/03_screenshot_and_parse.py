"""Task 1.4 Pipeline B — Playwright screenshot + Gemini Vision.

Targets restaurants where Pipeline A logged status='no_menu_found'.
Renders the /menu (or homepage) in headless Chromium, screenshots full
page, feeds PNG chunks to Gemini 2.5 Flash Vision, saves items with
source='gemini_screenshot'.

Usage (from backend/):
    python scripts/03_screenshot_and_parse.py --dry-run          # 10 restaurants, no DB writes
    python scripts/03_screenshot_and_parse.py                    # full run on remaining no_menu_found
    python scripts/03_screenshot_and_parse.py --limit 50         # cap at 50
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from google import genai
from google.genai import types as gtypes
from PIL import Image
from playwright.async_api import async_playwright
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import MenuItem  # noqa: E402


USER_AGENT = "BrokenLunchHackathonBot/1.0 (academic project)"
GEMINI_MODEL = "gemini-2.5-flash"
MAX_PRICE_CENTS = 1500


class ExtractedItem(BaseModel):
    name: str
    description: str | None = None
    price_cents: int = Field(ge=0)
    category: str | None = None
    confidence: float = 0.5


class ExtractedMenu(BaseModel):
    items: list[ExtractedItem] = []
    restaurant_name_detected: str | None = None
    warnings: list[str] = []


VISION_PROMPT_STRICT = (
    "These images are screenshots of a restaurant website (likely the menu page). "
    "Extract all menu items that have a clearly stated price.\n\n"
    "Rules:\n"
    "- Only include items priced $15.00 or less.\n"
    "- Skip drinks unless they are the main product (coffee/tea shops OK).\n"
    "- Skip 'market price' or 'varies' items.\n"
    "- For items with multiple sizes, create separate entries.\n"
    "- Translate prices to cents: $4.50 -> 450, $10 -> 1000.\n"
    "- Categorize each item as one of: burger, pizza, sandwich, pasta, salad, "
    "soup, mexican, asian, mediterranean, breakfast, dessert, drink, other.\n\n"
    "You MUST return a single top-level JSON object (NOT a bare array) with this "
    'exact schema:\n'
    '{"items": [{"name": "...", "description": null|"...", "price_cents": int, '
    '"category": "...", "confidence": 0.0..1.0}], '
    '"restaurant_name_detected": null|"...", "warnings": ["..."]}\n\n'
    "If no menu items are visible, return "
    '{"items": [], "restaurant_name_detected": null, "warnings": ["no_menu"]}.\n'
    "Return ONLY valid JSON — no prose, no markdown."
)


_gemini_client: genai.Client | None = None


def _get_gemini() -> genai.Client:
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=settings.gemini_api_key)
    return _gemini_client


def _coerce_extracted(raw: str) -> ExtractedMenu:
    data = json.loads(raw)
    if isinstance(data, list):
        # Gemini sometimes returns a bare list of items — wrap it.
        data = {"items": data, "restaurant_name_detected": None, "warnings": []}
    if not isinstance(data, dict):
        raise ValueError(f"unexpected top-level JSON type: {type(data).__name__}")
    data.setdefault("items", [])
    data.setdefault("warnings", [])
    data.setdefault("restaurant_name_detected", None)
    # Pre-clean each item: drop bad ones rather than fail the whole response.
    good_items = []
    for it in data.get("items", []):
        if not isinstance(it, dict):
            continue
        if "name" not in it or "price_cents" not in it:
            continue
        try:
            ExtractedItem(**it)
            good_items.append(it)
        except (ValidationError, TypeError, ValueError):
            continue
    data["items"] = good_items
    return ExtractedMenu(**data)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
async def gemini_vision_call(image_bytes_list: list[bytes]) -> ExtractedMenu:
    client = _get_gemini()
    parts = [gtypes.Part.from_bytes(data=b, mime_type="image/png") for b in image_bytes_list]
    resp = await client.aio.models.generate_content(
        model=GEMINI_MODEL,
        config=gtypes.GenerateContentConfig(response_mime_type="application/json"),
        contents=[*parts, VISION_PROMPT_STRICT],
    )
    return _coerce_extracted(getattr(resp, "text", "") or "")


SOURCE_LABEL = "gemini_screenshot"
VIEWPORT = {"width": 1280, "height": 900}
NAV_TIMEOUT_MS = 20000
LOAD_SETTLE_MS = 1500
MAX_IMAGE_DIM = 2000
MAX_CHUNKS_PER_PAGE = 4
CONCURRENCY = 2
LOG_PATH = Path("/tmp/pipeline_logs/pipeline_b.jsonl")
PER_RESTAURANT_SLEEP_S = 0.5


class Stats:
    def __init__(self) -> None:
        self.attempted = 0
        self.nav_failed = 0
        self.no_menu = 0
        self.success = 0
        self.items_saved = 0
        self.gemini_calls = 0
        self.gemini_errors = 0
        self.start_t = time.time()

    def eta_min(self, done: int, total: int) -> float:
        if done == 0:
            return 0.0
        elapsed = time.time() - self.start_t
        per = elapsed / done
        return (total - done) * per / 60.0


async def load_targets(db: AsyncSession, limit: int | None) -> list[tuple[str, str, str]]:
    """Restaurants where Pipeline A logged 'no_menu_found' and we haven't yet saved
    gemini_screenshot menu items."""
    q = text(
        """
        SELECT r.id::text, r.name, r.website
        FROM restaurants r
        JOIN crawl_log cl ON cl.restaurant_id = r.id AND cl.status = 'no_menu_found'
        WHERE r.website IS NOT NULL
          AND r.google_place_id NOT LIKE 'osm_%'
          AND NOT EXISTS (
              SELECT 1 FROM menu_items mi
              WHERE mi.restaurant_id = r.id AND mi.source = :src
          )
        ORDER BY r.id
        """
    )
    rows = (await db.execute(q, {"src": SOURCE_LABEL})).all()
    if limit:
        rows = rows[:limit]
    return [(r[0], r[1], r[2]) for r in rows]


async def _goto_with_fallback(page, website: str) -> str | None:
    """Try /menu first, fall back to homepage. Return final URL or None on fail."""
    parsed = urlparse(website)
    base = f"{parsed.scheme}://{parsed.netloc}"
    candidates = []
    if parsed.path and parsed.path not in ("/", ""):
        candidates.append(website)  # given URL is likely already a menu page
    candidates.append(base.rstrip("/") + "/menu")
    candidates.append(base.rstrip("/") + "/menus")
    candidates.append(base)
    seen: set[str] = set()
    for url in candidates:
        if url in seen:
            continue
        seen.add(url)
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            if resp and resp.ok:
                return url
        except Exception:
            continue
    return None


def _chunk_png(png_bytes: bytes, max_dim: int = MAX_IMAGE_DIM, max_chunks: int = MAX_CHUNKS_PER_PAGE) -> list[bytes]:
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    w, h = img.size
    # First shrink width if oversize
    if w > max_dim:
        ratio = max_dim / w
        img = img.resize((max_dim, int(h * ratio)), Image.LANCZOS)
        w, h = img.size
    chunks: list[bytes] = []
    if h <= max_dim:
        buf = io.BytesIO()
        img.save(buf, "PNG", optimize=True)
        return [buf.getvalue()]
    y = 0
    while y < h and len(chunks) < max_chunks:
        bottom = min(y + max_dim, h)
        crop = img.crop((0, y, w, bottom))
        buf = io.BytesIO()
        crop.save(buf, "PNG", optimize=True)
        chunks.append(buf.getvalue())
        y = bottom
    return chunks


async def screenshot_restaurant(browser, website: str) -> tuple[str | None, list[bytes]]:
    ctx = await browser.new_context(user_agent=USER_AGENT, viewport=VIEWPORT)
    page = await ctx.new_page()
    try:
        used_url = await _goto_with_fallback(page, website)
        if used_url is None:
            return None, []
        try:
            await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(LOAD_SETTLE_MS)
            await page.evaluate("() => window.scrollTo(0, 0)")
            await page.wait_for_timeout(300)
        except Exception:
            pass
        try:
            png = await page.screenshot(full_page=True, type="png", timeout=12000)
        except Exception:
            # fall back to viewport-only
            try:
                png = await page.screenshot(full_page=False, type="png", timeout=8000)
            except Exception:
                return used_url, []
        return used_url, _chunk_png(png)
    finally:
        await ctx.close()


def _filter_items(menu: ExtractedMenu) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for it in menu.items:
        if it.price_cents <= 0 or it.price_cents > MAX_PRICE_CENTS:
            continue
        key = f"{it.name.strip().lower()}|{it.price_cents}"
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "name": it.name.strip()[:255],
                "description": (it.description or "")[:500] or None,
                "price_cents": it.price_cents,
                "category": (it.category or "other")[:50],
            }
        )
    return out


async def persist(rid: str, items: list[dict[str, Any]]) -> None:
    if not items:
        return
    async with SessionLocal() as db:
        async with db.begin():
            rid_uuid = UUID(rid)
            for it in items:
                db.add(
                    MenuItem(
                        restaurant_id=rid_uuid,
                        name=it["name"],
                        description=it["description"],
                        price_cents=it["price_cents"],
                        category=it["category"],
                        source=SOURCE_LABEL,
                    )
                )


def _append_log(record: dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


async def process_one(
    idx: int,
    total: int,
    browser,
    rid: str,
    name: str,
    website: str,
    stats: Stats,
    dry_run: bool,
) -> None:
    stats.attempted += 1
    url, chunks = await screenshot_restaurant(browser, website)
    if url is None:
        stats.nav_failed += 1
        print(f"[{idx:4d}/{total}] nav_failed  items=0   {name[:44]:<44} -> {website}", flush=True)
        _append_log({"rid": rid, "name": name, "status": "nav_failed", "items": 0, "url": None})
        return
    if not chunks:
        stats.nav_failed += 1
        print(f"[{idx:4d}/{total}] screenshot_failed items=0   {name[:44]:<44} -> {url}", flush=True)
        _append_log({"rid": rid, "name": name, "status": "screenshot_failed", "items": 0, "url": url})
        return

    try:
        stats.gemini_calls += 1
        menu = await gemini_vision_call(chunks)
    except Exception as e:
        stats.gemini_errors += 1
        print(f"[{idx:4d}/{total}] gemini_error items=0   {name[:44]:<44} -> {url}\n    ! {str(e)[:200]}", flush=True)
        _append_log({"rid": rid, "name": name, "status": "gemini_error", "items": 0, "url": url, "err": str(e)[:300]})
        return

    items = _filter_items(menu)
    if not items:
        stats.no_menu += 1
        print(f"[{idx:4d}/{total}] no_items     items=0   {name[:44]:<44} -> {url}", flush=True)
        _append_log({"rid": rid, "name": name, "status": "no_items", "items": 0, "url": url,
                     "warnings": menu.warnings[:5] if menu.warnings else []})
        return

    if not dry_run:
        try:
            await persist(rid, items)
        except Exception as e:
            print(f"[{idx:4d}/{total}] persist_error items={len(items)}  {name[:44]:<44} -> {url}\n    ! {str(e)[:200]}", flush=True)
            _append_log({"rid": rid, "name": name, "status": "persist_error", "items": len(items), "url": url, "err": str(e)[:300]})
            return

    stats.success += 1
    stats.items_saved += len(items)
    tag = "success" if not dry_run else "dry_ok"
    sample = ", ".join(f"{it['name'][:18]}(${it['price_cents']/100:.2f})" for it in items[:3])
    print(f"[{idx:4d}/{total}] {tag:<12} items={len(items):<3} {name[:44]:<44} -> {url}\n    ~ {sample}", flush=True)
    _append_log({"rid": rid, "name": name, "status": tag, "items": len(items), "url": url})


async def progress_loop(stats: Stats, total: int, stop_evt: asyncio.Event) -> None:
    while not stop_evt.is_set():
        try:
            await asyncio.wait_for(stop_evt.wait(), timeout=60.0)
            return
        except asyncio.TimeoutError:
            pass
        done = stats.attempted
        elapsed = time.time() - stats.start_t
        print(
            f"[{int(elapsed//60):02d}:{int(elapsed%60):02d}] done={done}/{total} "
            f"success={stats.success} items={stats.items_saved} no_items={stats.no_menu} "
            f"nav_fail={stats.nav_failed} gem_err={stats.gemini_errors} "
            f"eta=~{stats.eta_min(done, total):.1f}m",
            flush=True,
        )


async def run(args: argparse.Namespace) -> None:
    stats = Stats()

    async with SessionLocal() as bootstrap:
        targets = await load_targets(bootstrap, limit=args.limit or (10 if args.dry_run else None))

    if not targets:
        print("[start] no targets (all no_menu_found rows already screenshotted)", flush=True)
        return

    print(
        f"[start] {len(targets)} targets concurrency={CONCURRENCY} dry_run={args.dry_run}",
        flush=True,
    )
    sem = asyncio.Semaphore(CONCURRENCY)
    stop_evt = asyncio.Event()
    progress_task = asyncio.create_task(progress_loop(stats, len(targets), stop_evt))

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            async def worker(i: int, t: tuple[str, str, str]) -> None:
                async with sem:
                    rid, name, website = t
                    try:
                        await asyncio.wait_for(
                            process_one(i + 1, len(targets), browser, rid, name, website, stats, args.dry_run),
                            timeout=90.0,
                        )
                    except asyncio.TimeoutError:
                        stats.nav_failed += 1
                        print(f"[{i+1}/{len(targets)}] timeout    {name[:44]} -> {website}", flush=True)
                    except Exception as e:
                        stats.nav_failed += 1
                        print(f"[{i+1}/{len(targets)}] worker_error {name[:44]} -> {str(e)[:200]}", flush=True)
                    await asyncio.sleep(PER_RESTAURANT_SLEEP_S)

            await asyncio.gather(*(worker(i, t) for i, t in enumerate(targets)))
        finally:
            await browser.close()

    stop_evt.set()
    await progress_task
    _print_report(stats, len(targets))


def _print_report(stats: Stats, n: int) -> None:
    elapsed = time.time() - stats.start_t
    print(
        "\n"
        "========================================================================\n"
        " Pipeline B — screenshot + Gemini Vision\n"
        "========================================================================\n"
        f"  Elapsed:            {elapsed:.1f}s\n"
        f"  Restaurants:        {stats.attempted}/{n}\n"
        f"  Success:            {stats.success}\n"
        f"  Menu items saved:   {stats.items_saved}\n"
        f"  No items extracted: {stats.no_menu}\n"
        f"  Nav / screenshot failed: {stats.nav_failed}\n"
        f"  Gemini calls:       {stats.gemini_calls} (errors {stats.gemini_errors})\n"
        f"  Gemini est. cost:   ${stats.gemini_calls * 0.0027:.3f}  (vision, rough avg)\n"
        "========================================================================",
        flush=True,
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="limit to 10, skip DB writes")
    p.add_argument("--limit", type=int, default=0, help="cap number of targets")
    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
