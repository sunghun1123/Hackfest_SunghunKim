"""Task 1.4 Pipeline D — aggressive PDF menu hunter.

For each restaurant with no menu items, HEAD-probe common PDF paths, scan
homepage + /menu for .pdf links, fetch the candidate, render with pypdfium2,
parse with Gemini Vision. Saves with source='gemini_pdf'.

Usage (from backend/):
    python scripts/05_pdf_hunter.py --dry-run         # 30 restaurants, no writes
    python scripts/05_pdf_hunter.py --limit 200
    python scripts/05_pdf_hunter.py                   # full run
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from uuid import UUID

import httpx
import pypdfium2 as pdfium
from bs4 import BeautifulSoup
from google import genai
from google.genai import types as gtypes
from PIL import Image
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
SOURCE_LABEL = "gemini_pdf"
MAX_PRICE_CENTS = 1500
CONCURRENCY = 4
PER_RESTAURANT_SLEEP_S = 0.3
PDF_MAX_BYTES = 15 * 1024 * 1024
PDF_MAX_PAGES = 6
PDF_RENDER_SCALE = 1.4
HTTP_TIMEOUT = 10.0
LOG_PATH = Path("/tmp/pipeline_logs/pipeline_d.jsonl")

COMMON_PDF_PATHS = [
    "/menu.pdf", "/menus.pdf",
    "/files/menu.pdf", "/uploads/menu.pdf",
    "/wp-content/uploads/menu.pdf", "/wp-content/uploads/menus.pdf",
    "/wp-content/uploads/Menu.pdf", "/wp-content/uploads/MENU.pdf",
    "/docs/menu.pdf", "/documents/menu.pdf",
    "/images/menu.pdf", "/assets/menu.pdf",
    "/menu/menu.pdf", "/pdf/menu.pdf",
    "/our-menu.pdf", "/dinner.pdf", "/lunch.pdf",
]

HOMEPAGE_SCAN_PATHS = ["", "/", "/menu", "/menus", "/food"]


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


PDF_VISION_PROMPT = (
    "These images are pages of a restaurant menu PDF. Extract all items with "
    "clearly stated prices.\n\n"
    "Rules:\n"
    "- Items priced $15.00 or less only.\n"
    "- Skip 'market price' / 'varies'.\n"
    "- Separate entries for size variants.\n"
    "- Prices in cents: $4.50 -> 450.\n"
    "- Categories: burger, pizza, sandwich, pasta, salad, soup, mexican, "
    "asian, mediterranean, breakfast, dessert, drink, other.\n\n"
    "Return a single top-level JSON object (NOT a bare array):\n"
    '{"items": [{"name": "...", "description": null|"...", "price_cents": int, '
    '"category": "...", "confidence": 0.0..1.0}], '
    '"restaurant_name_detected": null|"...", "warnings": ["..."]}\n'
    'If no items readable, return {"items":[], "restaurant_name_detected":null, "warnings":["unreadable"]}.\n'
    "Return ONLY valid JSON."
)


class Stats:
    def __init__(self) -> None:
        self.attempted = 0
        self.no_pdf = 0
        self.pdf_found = 0
        self.parse_fail = 0
        self.success = 0
        self.items_saved = 0
        self.gemini_calls = 0
        self.gemini_errors = 0
        self.start_t = time.time()

    def eta_min(self, done: int, total: int) -> float:
        if done == 0:
            return 0.0
        elapsed = time.time() - self.start_t
        return (total - done) * (elapsed / done) / 60.0


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
        contents=[*parts, PDF_VISION_PROMPT],
    )
    return _coerce_extracted(getattr(resp, "text", "") or "")


async def _head_is_pdf(client: httpx.AsyncClient, url: str) -> bool:
    try:
        r = await client.head(url, timeout=HTTP_TIMEOUT, follow_redirects=True)
        if r.status_code >= 400:
            return False
        ct = r.headers.get("content-type", "").lower()
        if "application/pdf" in ct:
            return True
        # Some servers don't reveal content-type on HEAD; also accept
        # .pdf paths with any non-error status.
        if url.lower().endswith(".pdf") and r.status_code == 200:
            return True
        return False
    except Exception:
        return False


async def _get_pdf_bytes(client: httpx.AsyncClient, url: str) -> bytes | None:
    try:
        r = await client.get(url, timeout=20.0, follow_redirects=True)
        if r.status_code >= 400:
            return None
        content = r.content[:PDF_MAX_BYTES]
        if content[:4] != b"%PDF":
            return None
        return content
    except Exception:
        return None


async def _scan_html_for_pdfs(
    client: httpx.AsyncClient, page_url: str
) -> list[str]:
    try:
        r = await client.get(page_url, timeout=HTTP_TIMEOUT, follow_redirects=True)
        if r.status_code >= 400:
            return []
        html = r.text
    except Exception:
        return []
    soup = BeautifulSoup(html, "html.parser")
    found: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        low = href.lower()
        if ".pdf" not in low:
            continue
        label = (a.get_text() or "").lower()
        # Score: menu-words in href or label
        if any(w in low or w in label for w in ("menu", "lunch", "dinner", "food", "takeout")):
            abs_url = urljoin(page_url, href)
            if abs_url not in found:
                found.append(abs_url)
        elif any(href.lower().endswith(s) for s in (".pdf",)):
            # bare .pdf link — lowest priority
            abs_url = urljoin(page_url, href)
            if abs_url not in found:
                found.append(abs_url)
    return found[:5]


async def find_menu_pdf(client: httpx.AsyncClient, website: str) -> str | None:
    parsed = urlparse(website)
    base = f"{parsed.scheme}://{parsed.netloc}"

    # 1) HEAD probes on common PDF paths
    for pth in COMMON_PDF_PATHS:
        url = base + pth
        if await _head_is_pdf(client, url):
            return url

    # 2) Scan homepage / /menu for <a href*=".pdf">
    for pth in HOMEPAGE_SCAN_PATHS:
        page_url = base + pth if pth else website
        candidates = await _scan_html_for_pdfs(client, page_url)
        for url in candidates:
            if await _head_is_pdf(client, url):
                return url

    return None


def pdf_to_images(pdf_bytes: bytes, max_pages: int = PDF_MAX_PAGES, scale: float = PDF_RENDER_SCALE) -> list[bytes]:
    try:
        pdf = pdfium.PdfDocument(pdf_bytes)
    except Exception:
        return []
    n = min(len(pdf), max_pages)
    images: list[bytes] = []
    for i in range(n):
        try:
            bm = pdf[i].render(scale=scale)
            pil = bm.to_pil().convert("RGB")
            if pil.width > 2000:
                ratio = 2000 / pil.width
                pil = pil.resize((2000, int(pil.height * ratio)), Image.LANCZOS)
            buf = io.BytesIO()
            pil.save(buf, "PNG", optimize=True)
            images.append(buf.getvalue())
        except Exception:
            continue
    return images


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
        SELECT r.id::text, r.name, r.website
        FROM restaurants r
        WHERE r.website IS NOT NULL
          AND r.google_place_id NOT LIKE 'osm_%'
          AND (SELECT COUNT(*) FROM menu_items mi WHERE mi.restaurant_id = r.id) = 0
        ORDER BY r.id
        """
    )
    rows = (await db.execute(q)).all()
    if limit:
        rows = rows[:limit]
    return [(r[0], r[1], r[2]) for r in rows]


async def process_one(
    idx: int,
    total: int,
    client: httpx.AsyncClient,
    rid: str,
    name: str,
    website: str,
    stats: Stats,
    dry_run: bool,
) -> None:
    stats.attempted += 1
    pdf_url = await find_menu_pdf(client, website)
    if pdf_url is None:
        stats.no_pdf += 1
        print(f"[{idx:4d}/{total}] no_pdf       items=0   {name[:44]:<44}", flush=True)
        _append_log({"rid": rid, "name": name, "status": "no_pdf"})
        return
    stats.pdf_found += 1
    pdf_bytes = await _get_pdf_bytes(client, pdf_url)
    if pdf_bytes is None:
        stats.parse_fail += 1
        print(f"[{idx:4d}/{total}] pdf_fetch_fail items=0 {name[:44]:<44} -> {pdf_url}", flush=True)
        _append_log({"rid": rid, "name": name, "status": "pdf_fetch_fail", "url": pdf_url})
        return
    images = pdf_to_images(pdf_bytes)
    if not images:
        stats.parse_fail += 1
        print(f"[{idx:4d}/{total}] pdf_render_fail items=0 {name[:44]:<44}", flush=True)
        _append_log({"rid": rid, "name": name, "status": "pdf_render_fail", "url": pdf_url})
        return

    try:
        stats.gemini_calls += 1
        menu = await gemini_vision_call(images)
    except Exception as e:
        stats.gemini_errors += 1
        print(f"[{idx:4d}/{total}] gemini_err  items=0    {name[:44]:<44}\n    ! {str(e)[:200]}", flush=True)
        _append_log({"rid": rid, "name": name, "status": "gemini_err", "url": pdf_url})
        return

    items = _filter_items(menu)
    if not items:
        stats.parse_fail += 1
        print(f"[{idx:4d}/{total}] pdf_no_items items=0   {name[:44]:<44} -> {pdf_url}", flush=True)
        _append_log({"rid": rid, "name": name, "status": "pdf_no_items", "url": pdf_url})
        return

    if not dry_run:
        try:
            await persist(rid, items)
        except Exception as e:
            print(f"[{idx:4d}/{total}] persist_err items={len(items)} {name[:44]:<44}\n    ! {str(e)[:200]}", flush=True)
            _append_log({"rid": rid, "name": name, "status": "persist_err"})
            return

    stats.success += 1
    stats.items_saved += len(items)
    tag = "success" if not dry_run else "dry_ok"
    sample = ", ".join(f"{it['name'][:18]}(${it['price_cents']/100:.2f})" for it in items[:3])
    print(f"[{idx:4d}/{total}] {tag:<12} items={len(items):<3} {name[:44]:<44} -> {pdf_url}\n    ~ {sample}", flush=True)
    _append_log({"rid": rid, "name": name, "status": tag, "items": len(items), "url": pdf_url})


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
            f"success={stats.success} items={stats.items_saved} pdf_found={stats.pdf_found} "
            f"no_pdf={stats.no_pdf} parse_fail={stats.parse_fail} gem_err={stats.gemini_errors} "
            f"eta=~{stats.eta_min(done, total):.1f}m",
            flush=True,
        )


async def run(args: argparse.Namespace) -> None:
    stats = Stats()
    async with SessionLocal() as boot:
        targets = await load_targets(boot, limit=args.limit or (30 if args.dry_run else None))

    if not targets:
        print("[start] no targets", flush=True)
        return

    print(f"[start] {len(targets)} targets concurrency={CONCURRENCY} dry_run={args.dry_run}", flush=True)
    sem = asyncio.Semaphore(CONCURRENCY)
    stop_evt = asyncio.Event()
    prog = asyncio.create_task(progress_loop(stats, len(targets), stop_evt))

    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
        async def worker(i: int, t: tuple[str, str, str]) -> None:
            async with sem:
                rid, name, website = t
                try:
                    await asyncio.wait_for(
                        process_one(i + 1, len(targets), client, rid, name, website, stats, args.dry_run),
                        timeout=60.0,
                    )
                except asyncio.TimeoutError:
                    stats.no_pdf += 1
                    print(f"[{i+1}/{len(targets)}] timeout    {name[:44]}", flush=True)
                except Exception as e:
                    stats.parse_fail += 1
                    print(f"[{i+1}/{len(targets)}] worker_err {name[:44]} -> {str(e)[:200]}", flush=True)
                await asyncio.sleep(PER_RESTAURANT_SLEEP_S)

        await asyncio.gather(*(worker(i, t) for i, t in enumerate(targets)))

    stop_evt.set()
    await prog
    _print_report(stats, len(targets))


def _print_report(stats: Stats, n: int) -> None:
    elapsed = time.time() - stats.start_t
    cost = stats.gemini_calls * 0.003
    print(
        "\n"
        "========================================================================\n"
        " Pipeline D — PDF Menu Hunter\n"
        "========================================================================\n"
        f"  Elapsed:            {elapsed:.1f}s\n"
        f"  Restaurants:        {stats.attempted}/{n}\n"
        f"  PDFs found:         {stats.pdf_found}\n"
        f"  Success:            {stats.success}\n"
        f"  Menu items saved:   {stats.items_saved}\n"
        f"  No PDF found:       {stats.no_pdf}\n"
        f"  Parse failures:     {stats.parse_fail}\n"
        f"  Gemini calls:       {stats.gemini_calls} (errors {stats.gemini_errors})\n"
        f"  Gemini est. cost:   ${cost:.3f}\n"
        "========================================================================",
        flush=True,
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="30 restaurants, no writes")
    p.add_argument("--limit", type=int, default=0, help="cap number of targets")
    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
