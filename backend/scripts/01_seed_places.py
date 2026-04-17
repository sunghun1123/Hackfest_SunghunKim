"""Task 1.3 — aggressive Grand Rapids restaurant collection.

Collects restaurants from:
  1. Google Places API (New) Text Search — 15 categories x 3 regions
  2. Google Places API (New) Nearby Search — 5x4 grid around GR center
  3. OpenStreetMap Overpass (free, source='osm') as a backup

Run from backend/:
    python scripts/01_seed_places.py                 # full collection
    python scripts/01_seed_places.py --dry-run --max-queries 1
    python scripts/01_seed_places.py --fresh         # wipe restaurants first
    python scripts/01_seed_places.py --categories-only   # skip grid + OSM
"""

from __future__ import annotations

import argparse
import asyncio
import math
import sys
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.models import Restaurant  # noqa: E402


PLACES_TEXT_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.nationalPhoneNumber",
        "places.websiteUri",
        "places.rating",
        "places.priceLevel",
        "places.regularOpeningHours",
        "places.types",
        "nextPageToken",
    ]
)

CATEGORIES = [
    "pizza", "mexican", "asian", "burger", "sandwich",
    "coffee", "sushi", "breakfast", "deli", "bakery",
    "mediterranean", "thai", "chinese", "indian", "chicken",
]
REGIONS = ["Grand Rapids MI", "Kentwood MI", "Wyoming MI"]

GR_LAT_CENTER, GR_LNG_CENTER = 42.9634, -85.6681
GRID_LATS = [GR_LAT_CENTER + d * 0.05 for d in (-2, -1, 0, 1, 2)]  # 5
GRID_LNGS = [GR_LNG_CENTER + d * 0.05 for d in (-1.5, -0.5, 0.5, 1.5)]  # 4
NEARBY_RADIUS_M = 2000.0

OVERPASS_QUERY = (
    "[out:json][timeout:60];"
    'node["amenity"="restaurant"](42.85,-85.80,43.05,-85.50);'
    "out body;"
)

CONCURRENCY = 3
MAX_PAGES = 3  # yields up to 60 results per text/nearby query
PAGE_TOKEN_DELAY_S = 2.0

PRICE_LEVEL_MAP = {
    "PRICE_LEVEL_FREE": 0,
    "PRICE_LEVEL_INEXPENSIVE": 1,
    "PRICE_LEVEL_MODERATE": 2,
    "PRICE_LEVEL_EXPENSIVE": 3,
    "PRICE_LEVEL_VERY_EXPENSIVE": 4,
}
SKIP_TYPES = {"restaurant", "food", "point_of_interest", "establishment"}

OnPage = Callable[[list[dict[str, Any]]], Awaitable[None]]


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def pick_category(types: list[str] | None) -> str | None:
    if not types:
        return None
    for t in types:
        if t not in SKIP_TYPES:
            return t
    return None


def place_to_row(place: dict[str, Any]) -> dict[str, Any] | None:
    place_id = place.get("id")
    name = (place.get("displayName") or {}).get("text")
    loc = place.get("location") or {}
    lat, lng = loc.get("latitude"), loc.get("longitude")
    if not place_id or not name or lat is None or lng is None:
        return None
    price_level_str = place.get("priceLevel")
    return {
        "google_place_id": place_id,
        "name": name[:255],
        "address": place.get("formattedAddress"),
        "lat": float(lat),
        "lng": float(lng),
        "phone": place.get("nationalPhoneNumber"),
        "website": place.get("websiteUri"),
        "google_rating": place.get("rating"),
        "price_level": PRICE_LEVEL_MAP.get(price_level_str) if price_level_str else None,
        "category": pick_category(place.get("types")),
        "hours_json": place.get("regularOpeningHours"),
    }


def osm_to_row(el: dict[str, Any]) -> dict[str, Any] | None:
    tags = el.get("tags") or {}
    name = tags.get("name")
    lat, lng = el.get("lat"), el.get("lon")
    osm_id = el.get("id")
    if not name or lat is None or lng is None or osm_id is None:
        return None
    return {
        "google_place_id": f"osm_{osm_id}",
        "name": name[:255],
        "address": tags.get("addr:full") or tags.get("addr:street"),
        "lat": float(lat),
        "lng": float(lng),
        "phone": tags.get("phone"),
        "website": tags.get("website"),
        "google_rating": None,
        "price_level": None,
        "category": tags.get("cuisine"),
        "hours_json": None,
    }


class Stats:
    def __init__(self) -> None:
        self.text_calls = 0
        self.nearby_calls = 0
        self.osm_calls = 0
        self.errors = 0
        self.inserted_google = 0
        self.inserted_osm = 0
        self.with_website_seen = 0


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(
        (httpx.HTTPStatusError, httpx.ReadTimeout, httpx.ConnectError)
    ),
    reraise=True,
)
async def _post_places(client: httpx.AsyncClient, url: str, body: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.google_places_api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    resp = await client.post(url, headers=headers, json=body, timeout=30.0)
    if resp.status_code in (429, 500, 502, 503, 504):
        raise httpx.HTTPStatusError(
            f"retryable {resp.status_code}", request=resp.request, response=resp
        )
    resp.raise_for_status()
    return resp.json()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=5, max=30),
    retry=retry_if_exception_type(
        (httpx.HTTPStatusError, httpx.ReadTimeout, httpx.ConnectError)
    ),
    reraise=True,
)
async def fetch_osm(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    resp = await client.post(OVERPASS_URL, data={"data": OVERPASS_QUERY}, timeout=120.0)
    resp.raise_for_status()
    return resp.json().get("elements", [])


async def load_existing_place_ids(db: AsyncSession) -> set[str]:
    result = await db.execute(select(Restaurant.google_place_id))
    return {row[0] for row in result}


async def truncate_restaurants(db: AsyncSession) -> None:
    await db.execute(text("TRUNCATE restaurants RESTART IDENTITY CASCADE"))
    await db.commit()


async def insert_batch(
    db: AsyncSession, rows: list[dict[str, Any]], *, existing: set[str]
) -> int:
    new_rows = [r for r in rows if r["google_place_id"] not in existing]
    if not new_rows:
        return 0
    stmt = (
        pg_insert(Restaurant)
        .values(new_rows)
        .on_conflict_do_nothing(index_elements=["google_place_id"])
    )
    result = await db.execute(stmt)
    await db.commit()
    for r in new_rows:
        existing.add(r["google_place_id"])
    return result.rowcount if result.rowcount is not None else len(new_rows)


async def paginate_text_search(
    client: httpx.AsyncClient,
    query: str,
    *,
    on_page: OnPage,
    stats: Stats,
) -> None:
    page_token: str | None = None
    for page in range(MAX_PAGES):
        body: dict[str, Any] = {"textQuery": query, "pageSize": 20}
        if page_token:
            body["pageToken"] = page_token
        try:
            data = await _post_places(client, PLACES_TEXT_URL, body)
            stats.text_calls += 1
        except Exception as e:
            stats.errors += 1
            print(f"[text] {query!r} page {page + 1} failed: {e}", flush=True)
            return
        places = data.get("places") or []
        if places:
            await on_page(places)
        page_token = data.get("nextPageToken")
        if not page_token:
            return
        await asyncio.sleep(PAGE_TOKEN_DELAY_S)


async def paginate_nearby_search(
    client: httpx.AsyncClient,
    lat: float,
    lng: float,
    *,
    on_page: OnPage,
    stats: Stats,
) -> None:
    page_token: str | None = None
    for page in range(MAX_PAGES):
        body: dict[str, Any] = {
            "includedTypes": ["restaurant"],
            "maxResultCount": 20,
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
                    "radius": NEARBY_RADIUS_M,
                }
            },
        }
        if page_token:
            body["pageToken"] = page_token
        try:
            data = await _post_places(client, PLACES_NEARBY_URL, body)
            stats.nearby_calls += 1
        except Exception as e:
            stats.errors += 1
            print(f"[nearby] ({lat:.3f},{lng:.3f}) page {page + 1} failed: {e}", flush=True)
            return
        places = data.get("places") or []
        if places:
            await on_page(places)
        page_token = data.get("nextPageToken")
        if not page_token:
            return
        await asyncio.sleep(PAGE_TOKEN_DELAY_S)


def dedup_osm(
    osm_rows: list[dict[str, Any]],
    google_names: dict[str, list[tuple[float, float]]],
) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for r in osm_rows:
        key = r["name"].strip().lower()
        candidates = google_names.get(key, [])
        if any(haversine_m(r["lat"], r["lng"], glat, glng) < 50.0 for glat, glng in candidates):
            continue
        kept.append(r)
    return kept


async def run(args: argparse.Namespace) -> None:
    stats = Stats()
    start = time.time()
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async with SessionLocal() as bootstrap:
        if args.fresh and not args.dry_run:
            print("[fresh] TRUNCATE restaurants CASCADE", flush=True)
            await truncate_restaurants(bootstrap)
        existing: set[str] = set() if args.fresh else await load_existing_place_ids(bootstrap)
        print(f"[resume] {len(existing)} existing place_ids in DB - skipping those", flush=True)

    insert_lock = asyncio.Lock()
    google_names: dict[str, list[tuple[float, float]]] = {}
    progress_milestone = {"last": 0}

    async def on_page(places: list[dict[str, Any]]) -> None:
        rows = [r for r in (place_to_row(p) for p in places) if r]
        if not rows:
            return
        for r in rows:
            google_names.setdefault(r["name"].strip().lower(), []).append((r["lat"], r["lng"]))
            if r.get("website"):
                stats.with_website_seen += 1

        if args.dry_run:
            for r in rows[:5]:
                site = "Y" if r.get("website") else "-"
                cat = r.get("category") or "-"
                print(
                    f"  [dry] {r['name'][:40]:<40}  cat={cat:<25}  "
                    f"({r['lat']:.4f},{r['lng']:.4f})  site={site}  price={r.get('price_level')}",
                    flush=True,
                )
            if len(rows) > 5:
                print(f"  [dry] ... +{len(rows) - 5} more", flush=True)
            return

        async with insert_lock:
            async with SessionLocal() as db:
                inserted = await insert_batch(db, rows, existing=existing)
        stats.inserted_google += inserted
        if stats.inserted_google // 10 > progress_milestone["last"]:
            progress_milestone["last"] = stats.inserted_google // 10
            print(
                f"[progress] google={stats.inserted_google} "
                f"text_calls={stats.text_calls} nearby_calls={stats.nearby_calls} "
                f"errors={stats.errors}",
                flush=True,
            )

    async def worker_text(client: httpx.AsyncClient, query: str) -> None:
        async with semaphore:
            print(f"[text] {query}", flush=True)
            await paginate_text_search(client, query, on_page=on_page, stats=stats)

    async def worker_nearby(client: httpx.AsyncClient, lat: float, lng: float) -> None:
        async with semaphore:
            print(f"[nearby] ({lat:.4f},{lng:.4f})", flush=True)
            await paginate_nearby_search(client, lat, lng, on_page=on_page, stats=stats)

    timeout = httpx.Timeout(30.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        tasks: list[asyncio.Task[None]] = []
        for c in CATEGORIES:
            for region in REGIONS:
                tasks.append(asyncio.create_task(worker_text(client, f"{c} in {region}")))
        if not args.categories_only:
            for la in GRID_LATS:
                for ln in GRID_LNGS:
                    tasks.append(asyncio.create_task(worker_nearby(client, la, ln)))

        if args.max_queries is not None:
            active = tasks[: args.max_queries]
            for t in tasks[args.max_queries :]:
                t.cancel()
            await asyncio.gather(*active, return_exceptions=True)
        else:
            await asyncio.gather(*tasks, return_exceptions=True)

        if not args.categories_only and not args.dry_run and args.max_queries is None:
            print("[osm] fetching OpenStreetMap via Overpass...", flush=True)
            try:
                elements = await fetch_osm(client)
                stats.osm_calls += 1
                osm_rows = [r for r in (osm_to_row(e) for e in elements) if r]
                kept = dedup_osm(osm_rows, google_names)
                print(
                    f"[osm] nodes={len(elements)} usable={len(osm_rows)} new_after_dedup={len(kept)}",
                    flush=True,
                )
                CHUNK = 100
                for i in range(0, len(kept), CHUNK):
                    async with SessionLocal() as db:
                        inserted = await insert_batch(db, kept[i : i + CHUNK], existing=existing)
                    stats.inserted_osm += inserted
            except Exception as e:
                stats.errors += 1
                print(f"[osm] failed: {e}", flush=True)

    await _print_report(stats, start, dry_run=args.dry_run)
    await engine.dispose()


async def _print_report(stats: Stats, start_t: float, *, dry_run: bool) -> None:
    elapsed = time.time() - start_t
    print("\n" + "=" * 72)
    print(" Task 1.3 - Places API seed report")
    print("=" * 72)
    print(f"  Elapsed:            {elapsed:.1f}s")
    print(f"  Text-search calls:  {stats.text_calls}")
    print(f"  Nearby calls:       {stats.nearby_calls}")
    print(f"  OSM calls:          {stats.osm_calls}")
    print(f"  Errors:             {stats.errors}")
    print(f"  Inserted Google:    {stats.inserted_google}")
    print(f"  Inserted OSM:       {stats.inserted_osm}")
    print(f"  With website (seen):{stats.with_website_seen}")

    if not dry_run:
        async with SessionLocal() as db:
            total = (await db.execute(text("SELECT COUNT(*) FROM restaurants"))).scalar_one()
            osm_n = (
                await db.execute(
                    text("SELECT COUNT(*) FROM restaurants WHERE google_place_id LIKE 'osm_%'")
                )
            ).scalar_one()
            web_n = (
                await db.execute(text("SELECT COUNT(*) FROM restaurants WHERE website IS NOT NULL"))
            ).scalar_one()
            cats = (
                await db.execute(
                    text(
                        "SELECT category, COUNT(*) AS n FROM restaurants "
                        "WHERE category IS NOT NULL "
                        "GROUP BY category ORDER BY n DESC LIMIT 10"
                    )
                )
            ).all()
            bbox = (
                await db.execute(
                    text("SELECT MIN(lat), MAX(lat), MIN(lng), MAX(lng) FROM restaurants")
                )
            ).one()

        print(f"\n  DB total restaurants:   {total}")
        print(f"  DB from OSM:            {osm_n}")
        print(f"  DB from Places:         {total - osm_n}")
        print(f"  DB with website:        {web_n}")
        print("\n  Top 10 categories:")
        for cat, n in cats:
            print(f"    {cat:<30} {n}")
        if bbox and bbox[0] is not None:
            print("\n  Bounding box:")
            print(f"    lat: [{float(bbox[0]):.5f}, {float(bbox[1]):.5f}]")
            print(f"    lng: [{float(bbox[2]):.5f}, {float(bbox[3]):.5f}]")

    billable = stats.text_calls + stats.nearby_calls
    est_cost = billable * 32.0 / 1000.0
    print(f"\n  Estimated Places cost:  ${est_cost:.2f}  ({billable} billable calls @ $32/1k)")
    print("  ($200 free monthly credit covers this easily.)")
    print("=" * 72)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Task 1.3 aggressive Places seed")
    p.add_argument("--dry-run", action="store_true", help="Fetch but do not write to DB")
    p.add_argument("--fresh", action="store_true", help="TRUNCATE restaurants CASCADE first")
    p.add_argument("--categories-only", action="store_true", help="Skip nearby grid and OSM")
    p.add_argument(
        "--max-queries",
        type=int,
        default=None,
        help="Cap number of Places queries (dev/testing)",
    )
    return p.parse_args()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run(parse_args()))
