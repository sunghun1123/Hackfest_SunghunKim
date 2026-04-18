"""Task 1.4 Pipeline C — Google Places Photos mining.

For each restaurant without menu items (and with a google_place_id), fetch
Place Details → photos array, pull each photo, ask Gemini Vision 'is this
a menu?' (yes/no), then parse yes-photos with the standard menu prompt.
Saves items with source='gemini_places_photo'.

Usage (from backend/):
    python scripts/04_places_photos.py --dry-run         # 20 restaurants, no writes
    python scripts/04_places_photos.py --limit 200       # cap
    python scripts/04_places_photos.py                   # full run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from google import genai
from google.genai import types as gtypes
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import MenuItem  # noqa: E402


PLACES_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"
PHOTO_MEDIA_URL = "https://places.googleapis.com/v1/{photo_name}/media"
PLACES_DETAILS_FIELD_MASK = "id,displayName,photos"

MAX_PHOTOS_PER_RESTAURANT = 4
PHOTO_MAX_WIDTH = 1600
SOURCE_LABEL = "gemini_places_photo"
CONCURRENCY = 3
GEMINI_MODEL = "gemini-2.5-flash"
MAX_PRICE_CENTS = 1500
PER_RESTAURANT_SLEEP_S = 0.3
LOG_PATH = Path("/tmp/pipeline_logs/pipeline_c.jsonl")


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


VISION_MENU_CHECK_PROMPT = (
    "Is this image a photograph of a restaurant menu with visible prices? "
    "Reply with one word only: YES or NO."
)

VISION_PARSE_PROMPT = (
    "This image is a photograph of a restaurant menu. Extract all items with "
    "visible prices.\n\n"
    "Rules:\n"
    "- Only include items priced $15.00 or less.\n"
    "- Skip drinks unless they are the main product.\n"
    "- Skip 'market price' or 'varies' items.\n"
    "- For items with multiple sizes, create separate entries.\n"
    "- Prices in cents: $4.50 -> 450.\n"
    "- Categorize as: burger, pizza, sandwich, pasta, salad, soup, mexican, "
    "asian, mediterranean, breakfast, dessert, drink, other.\n\n"
    "Return a single top-level JSON object (NOT a bare array):\n"
    '{"items": [{"name": "...", "description": null|"...", "price_cents": int, '
    '"category": "...", "confidence": 0.0..1.0}], '
    '"restaurant_name_detected": null|"...", "warnings": ["..."]}\n'
    "If no items are readable, return "
    '{"items": [], "restaurant_name_detected": null, "warnings": ["unreadable"]}.\n'
    "Return ONLY valid JSON."
)


class Stats:
    def __init__(self) -> None:
        self.attempted = 0
        self.no_photos = 0
        self.no_menu_photos = 0
        self.success = 0
        self.items_saved = 0
        self.details_calls = 0
        self.photo_fetches = 0
        self.gemini_check_calls = 0
        self.gemini_parse_calls = 0
        self.gemini_errors = 0
        self.http_errors = 0
        self.start_t = time.time()

    def eta_min(self, done: int, total: int) -> float:
        if done == 0:
            return 0.0
        elapsed = time.time() - self.start_t
        per = elapsed / done
        return (total - done) * per / 60.0


_gemini_client: genai.Client | None = None


def _get_gemini() -> genai.Client:
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=settings.gemini_api_key)
    return _gemini_client


def _coerce_extracted(raw: str) -> ExtractedMenu:
    data = json.loads(raw)
    if isinstance(data, list):
        data = {"items": data, "restaurant_name_detected": None, "warnings": []}
    if not isinstance(data, dict):
        raise ValueError(f"top-level JSON type: {type(data).__name__}")
    data.setdefault("items", [])
    data.setdefault("warnings", [])
    data.setdefault("restaurant_name_detected", None)
    good = []
    for it in data.get("items", []):
        if not isinstance(it, dict) or "name" not in it or "price_cents" not in it:
            continue
        try:
            ExtractedItem(**it)
            good.append(it)
        except (ValidationError, TypeError, ValueError):
            continue
    data["items"] = good
    return ExtractedMenu(**data)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=20),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
async def gemini_is_menu(img_bytes: bytes) -> bool:
    client = _get_gemini()
    part = gtypes.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")
    resp = await client.aio.models.generate_content(
        model=GEMINI_MODEL,
        contents=[part, VISION_MENU_CHECK_PROMPT],
    )
    txt = (getattr(resp, "text", "") or "").strip().upper()
    return txt.startswith("YES")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
async def gemini_parse_menu(img_bytes: bytes) -> ExtractedMenu:
    client = _get_gemini()
    part = gtypes.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")
    resp = await client.aio.models.generate_content(
        model=GEMINI_MODEL,
        config=gtypes.GenerateContentConfig(response_mime_type="application/json"),
        contents=[part, VISION_PARSE_PROMPT],
    )
    return _coerce_extracted(getattr(resp, "text", "") or "")


async def fetch_place_details(
    client: httpx.AsyncClient, place_id: str
) -> list[str] | None:
    """Return list of photo resource names, or None if request failed."""
    url = PLACES_DETAILS_URL.format(place_id=place_id)
    headers = {
        "X-Goog-Api-Key": settings.google_places_api_key,
        "X-Goog-FieldMask": PLACES_DETAILS_FIELD_MASK,
    }
    try:
        r = await client.get(url, headers=headers, timeout=15.0)
        if r.status_code != 200:
            return None
        data = r.json()
    except Exception:
        return None
    photos = data.get("photos") or []
    return [p.get("name") for p in photos if p.get("name")]


async def fetch_photo_bytes(
    client: httpx.AsyncClient, photo_name: str
) -> bytes | None:
    url = PHOTO_MEDIA_URL.format(photo_name=photo_name)
    headers = {"X-Goog-Api-Key": settings.google_places_api_key}
    params = {"maxWidthPx": PHOTO_MAX_WIDTH}
    try:
        r = await client.get(url, headers=headers, params=params, timeout=20.0, follow_redirects=True)
        if r.status_code != 200:
            return None
        return r.content
    except Exception:
        return None


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


def _append_log(rec: dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


async def load_targets(db: AsyncSession, limit: int | None) -> list[tuple[str, str, str]]:
    q = text(
        """
        SELECT r.id::text, r.name, r.google_place_id
        FROM restaurants r
        WHERE r.google_place_id NOT LIKE 'osm_%'
          AND NOT EXISTS (
              SELECT 1 FROM menu_items mi
              WHERE mi.restaurant_id = r.id AND mi.source = :src
          )
          AND (SELECT COUNT(*) FROM menu_items mi2 WHERE mi2.restaurant_id = r.id) = 0
        ORDER BY r.id
        """
    )
    rows = (await db.execute(q, {"src": SOURCE_LABEL})).all()
    if limit:
        rows = rows[:limit]
    return [(r[0], r[1], r[2]) for r in rows]


async def process_one(
    idx: int,
    total: int,
    http: httpx.AsyncClient,
    rid: str,
    name: str,
    place_id: str,
    stats: Stats,
    dry_run: bool,
) -> None:
    stats.attempted += 1
    stats.details_calls += 1
    photo_names = await fetch_place_details(http, place_id)
    if photo_names is None:
        stats.http_errors += 1
        print(f"[{idx:4d}/{total}] details_fail items=0   {name[:44]:<44}", flush=True)
        _append_log({"rid": rid, "name": name, "status": "details_fail"})
        return
    if not photo_names:
        stats.no_photos += 1
        print(f"[{idx:4d}/{total}] no_photos    items=0   {name[:44]:<44}", flush=True)
        _append_log({"rid": rid, "name": name, "status": "no_photos"})
        return

    to_check = photo_names[:MAX_PHOTOS_PER_RESTAURANT]
    menu_photos: list[bytes] = []
    for pn in to_check:
        img = await fetch_photo_bytes(http, pn)
        if img is None:
            continue
        stats.photo_fetches += 1
        try:
            stats.gemini_check_calls += 1
            is_menu = await gemini_is_menu(img)
        except Exception:
            stats.gemini_errors += 1
            continue
        if is_menu:
            menu_photos.append(img)

    if not menu_photos:
        stats.no_menu_photos += 1
        print(f"[{idx:4d}/{total}] no_menu_pic  items=0   {name[:44]:<44} (checked {len(to_check)})", flush=True)
        _append_log({"rid": rid, "name": name, "status": "no_menu_pic", "checked": len(to_check)})
        return

    all_items: list[dict[str, Any]] = []
    for img in menu_photos[:3]:  # parse at most 3 menu photos per restaurant
        try:
            stats.gemini_parse_calls += 1
            menu = await gemini_parse_menu(img)
        except Exception as e:
            stats.gemini_errors += 1
            print(f"    ! parse err: {str(e)[:120]}", flush=True)
            continue
        all_items.extend(_filter_items(menu))

    # dedup across photos
    seen: set[str] = set()
    unique_items: list[dict[str, Any]] = []
    for it in all_items:
        k = f"{it['name'].lower()}|{it['price_cents']}"
        if k in seen:
            continue
        seen.add(k)
        unique_items.append(it)

    if not unique_items:
        stats.no_menu_photos += 1
        print(f"[{idx:4d}/{total}] menu_pic_empty items=0  {name[:44]:<44}", flush=True)
        _append_log({"rid": rid, "name": name, "status": "menu_pic_empty"})
        return

    if not dry_run:
        try:
            await persist(rid, unique_items)
        except Exception as e:
            print(f"[{idx:4d}/{total}] persist_error items={len(unique_items)} {name[:44]:<44}\n    ! {str(e)[:200]}", flush=True)
            _append_log({"rid": rid, "name": name, "status": "persist_error", "err": str(e)[:300]})
            return

    stats.success += 1
    stats.items_saved += len(unique_items)
    tag = "success" if not dry_run else "dry_ok"
    sample = ", ".join(f"{it['name'][:18]}(${it['price_cents']/100:.2f})" for it in unique_items[:3])
    print(f"[{idx:4d}/{total}] {tag:<12} items={len(unique_items):<3} {name[:44]:<44}\n    ~ {sample}", flush=True)
    _append_log({"rid": rid, "name": name, "status": tag, "items": len(unique_items)})


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
            f"success={stats.success} items={stats.items_saved} "
            f"no_photos={stats.no_photos} no_menu_pic={stats.no_menu_photos} "
            f"http_err={stats.http_errors} gem_err={stats.gemini_errors} "
            f"eta=~{stats.eta_min(done, total):.1f}m",
            flush=True,
        )


async def run(args: argparse.Namespace) -> None:
    stats = Stats()
    async with SessionLocal() as boot:
        targets = await load_targets(boot, limit=args.limit or (20 if args.dry_run else None))

    if not targets:
        print("[start] no targets", flush=True)
        return

    print(f"[start] {len(targets)} targets concurrency={CONCURRENCY} dry_run={args.dry_run}", flush=True)
    sem = asyncio.Semaphore(CONCURRENCY)
    stop_evt = asyncio.Event()
    prog = asyncio.create_task(progress_loop(stats, len(targets), stop_evt))

    async with httpx.AsyncClient() as http:
        async def worker(i: int, t: tuple[str, str, str]) -> None:
            async with sem:
                rid, name, pid = t
                try:
                    await asyncio.wait_for(
                        process_one(i + 1, len(targets), http, rid, name, pid, stats, args.dry_run),
                        timeout=90.0,
                    )
                except asyncio.TimeoutError:
                    stats.http_errors += 1
                    print(f"[{i+1}/{len(targets)}] timeout     {name[:44]}", flush=True)
                except Exception as e:
                    stats.http_errors += 1
                    print(f"[{i+1}/{len(targets)}] worker_err  {name[:44]} -> {str(e)[:200]}", flush=True)
                await asyncio.sleep(PER_RESTAURANT_SLEEP_S)

        await asyncio.gather(*(worker(i, t) for i, t in enumerate(targets)))

    stop_evt.set()
    await prog
    _print_report(stats, len(targets))


def _print_report(stats: Stats, n: int) -> None:
    elapsed = time.time() - stats.start_t
    # Places API: $5/1000 details, $7/1000 photos. Gemini Flash ~$0.001 per small-image call.
    cost = (stats.details_calls * 0.005 + stats.photo_fetches * 0.007
            + (stats.gemini_check_calls + stats.gemini_parse_calls) * 0.002)
    print(
        "\n"
        "========================================================================\n"
        " Pipeline C — Places Photos Mining\n"
        "========================================================================\n"
        f"  Elapsed:            {elapsed:.1f}s\n"
        f"  Restaurants:        {stats.attempted}/{n}\n"
        f"  Success:            {stats.success}\n"
        f"  Menu items saved:   {stats.items_saved}\n"
        f"  No photos:          {stats.no_photos}\n"
        f"  No menu-like photo: {stats.no_menu_photos}\n"
        f"  HTTP / timeout errs: {stats.http_errors}\n"
        f"  Places Details calls: {stats.details_calls}\n"
        f"  Photo fetches:      {stats.photo_fetches}\n"
        f"  Gemini calls:       {stats.gemini_check_calls + stats.gemini_parse_calls} "
        f"(check {stats.gemini_check_calls}, parse {stats.gemini_parse_calls}, errors {stats.gemini_errors})\n"
        f"  Est. total cost:    ${cost:.2f}  (Places + Gemini combined)\n"
        "========================================================================",
        flush=True,
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="20 restaurants, no writes")
    p.add_argument("--limit", type=int, default=0, help="cap number of targets")
    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
