"""Task 1.4 - crawl restaurant websites and parse menus with Gemini 2.5 Flash.

Usage (from backend/):
    python scripts/02_crawl_and_parse.py --dry-run         # 5 restaurants, no DB writes
    python scripts/02_crawl_and_parse.py                   # full run
    python scripts/02_crawl_and_parse.py --retry-failed    # parse_failed rows only
    python scripts/02_crawl_and_parse.py --fresh           # wipe crawl_log + gemini_web menu_items
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
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
from bs4 import BeautifulSoup
from google import genai
from google.genai import types as gtypes
from protego import Protego
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text
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
from app.models import CrawlLog, MenuItem  # noqa: E402


USER_AGENT = "BrokenLunchHackathonBot/1.0 (academic project)"
USER_AGENT_PRODUCT = "BrokenLunchHackathonBot"

MENU_PATHS = [
    "/menu", "/menus", "/food", "/our-menu", "/menu.pdf", "/menu.html",
    "/dining", "/dinner", "/lunch", "/takeout", "/takeout-menu", "/order",
]

HTTP_TIMEOUT = 10.0
MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_TEXT_FOR_GEMINI = 60_000

CONCURRENCY = 3
PER_RESTAURANT_SLEEP_S = 2.0
MAX_PRICE_CENTS = 1500  # $15 per DB constraint

GEMINI_MODEL = "gemini-2.5-flash"

SYSTEM_INSTRUCTION = (
    "You are a menu data extractor. You receive HTML text content from a "
    "restaurant's menu page and must extract all menu items with prices. "
    "You MUST respond with valid JSON only. No prose, no markdown code fences."
)

_USER_PROMPT_HEAD = (
    "Below is HTML/text content from a restaurant's menu page.\n"
    "Extract all food items with clearly stated prices.\n\n"
    "Rules:\n"
    "- Only include items priced $15.00 or less (our app scope).\n"
    "- Skip drinks unless they are the main item (coffee/tea shops OK).\n"
    "- Skip 'market price' or 'varies' items.\n"
    "- For items with multiple sizes, create separate entries.\n"
    "- Translate prices to cents: $4.50 -> 450, $10 -> 1000.\n"
    "- Categorize each item as one of: burger, pizza, sandwich, pasta, salad, "
    "soup, mexican, asian, mediterranean, breakfast, dessert, drink, other.\n\n"
    "Output JSON schema:\n"
    '{"items":[{"name":"...","description":"..."|null,"price_cents":int,'
    '"category":"...","confidence":0..1}],'
    '"restaurant_name_detected":"..."|null,"warnings":["..."]}\n\n'
    "If there is no menu content, return an empty items array with "
    'warnings=["no_menu"].\n\n'
    "Content:\n---\n"
)
_USER_PROMPT_TAIL = "\n---"


def build_user_prompt(content: str) -> str:
    return f"{_USER_PROMPT_HEAD}{content}{_USER_PROMPT_TAIL}"

VISION_PROMPT = (
    "These images are pages of a restaurant menu PDF. Extract all food items "
    "with clearly stated prices using the same rules: items <= $15, prices in "
    "cents, include category. Output the same JSON schema as above."
)


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


class Stats:
    def __init__(self) -> None:
        self.attempted = 0
        self.robots_blocked = 0
        self.no_menu = 0
        self.http_error = 0
        self.parse_failed = 0
        self.success = 0
        self.items_saved = 0
        self.gemini_calls = 0
        self.gemini_errors = 0
        self.start_t = time.time()


def clean_html_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # Keep JSON-LD payloads (Schema.org Menu data often lives here on SPA sites);
    # drop everything else inside <script>/<style>/etc.
    jsonld_blocks: list[str] = []
    for tag in soup.find_all("script"):
        if (tag.get("type") or "").lower() == "application/ld+json":
            raw = (tag.string or tag.get_text() or "").strip()
            if raw:
                jsonld_blocks.append(raw)
        tag.decompose()
    for tag in soup(["style", "noscript", "nav", "header", "footer"]):
        tag.decompose()
    visible = soup.get_text(separator=" ", strip=True)
    visible = re.sub(r"\s+", " ", visible)
    pieces: list[str] = []
    if jsonld_blocks:
        pieces.append("[JSON-LD]\n" + "\n---\n".join(jsonld_blocks))
    if visible:
        pieces.append("[VISIBLE TEXT]\n" + visible)
    return "\n\n".join(pieces)[:MAX_TEXT_FOR_GEMINI]


def find_menu_links_in_html(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    hits: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        label = (a.get_text(" ", strip=True) or "").lower()
        href_low = href.lower()
        if any(
            k in href_low or k in label
            for k in ("menu", "/food", "dinner", "lunch", "takeout", "order")
        ):
            if href.startswith("#"):
                continue
            hits.append(urljoin(base_url, href))
    seen: set[str] = set()
    uniq: list[str] = []
    for u in hits:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq[:5]


def pdf_to_text(pdf_bytes: bytes) -> str:
    import pdfplumber

    chunks: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for i, page in enumerate(pdf.pages):
            if i >= 6:
                break
            t = page.extract_text() or ""
            if t:
                chunks.append(t)
    combined = re.sub(r"\s+", " ", "\n\n".join(chunks))
    return combined[:MAX_TEXT_FOR_GEMINI]


def pdf_to_images(pdf_bytes: bytes, max_pages: int = 5, scale: float = 1.5) -> list[bytes]:
    import pypdfium2 as pdfium

    out: list[bytes] = []
    pdf = pdfium.PdfDocument(pdf_bytes)
    for i, page in enumerate(pdf):
        if i >= max_pages:
            break
        bitmap = page.render(scale=scale)
        pil = bitmap.to_pil()
        buf = io.BytesIO()
        pil.save(buf, format="PNG", optimize=True)
        out.append(buf.getvalue())
    return out


_gemini_client: genai.Client | None = None


def get_gemini() -> genai.Client:
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=settings.gemini_api_key)
    return _gemini_client


def _parse_extracted(resp: Any) -> ExtractedMenu:
    raw = getattr(resp, "text", None) or ""
    data = json.loads(raw)
    return ExtractedMenu(**data)


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((json.JSONDecodeError, ValidationError, Exception)),
    reraise=True,
)
async def gemini_text_call(text_content: str) -> ExtractedMenu:
    client = get_gemini()
    resp = await client.aio.models.generate_content(
        model=GEMINI_MODEL,
        config=gtypes.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
        ),
        contents=[build_user_prompt(text_content)],
    )
    return _parse_extracted(resp)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((json.JSONDecodeError, ValidationError, Exception)),
    reraise=True,
)
async def gemini_vision_call(image_bytes_list: list[bytes]) -> ExtractedMenu:
    client = get_gemini()
    parts = [gtypes.Part.from_bytes(data=b, mime_type="image/png") for b in image_bytes_list]
    resp = await client.aio.models.generate_content(
        model=GEMINI_MODEL,
        config=gtypes.GenerateContentConfig(response_mime_type="application/json"),
        contents=[*parts, VISION_PROMPT],
    )
    return _parse_extracted(resp)


async def check_robots(client: httpx.AsyncClient, url: str) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        r = await client.get(robots_url, timeout=HTTP_TIMEOUT)
        if r.status_code >= 400:
            return True
        rp = Protego.parse(r.text)
        return rp.can_fetch(url, USER_AGENT_PRODUCT)
    except Exception:
        return True


async def _fetch(
    client: httpx.AsyncClient, url: str, max_bytes: int
) -> tuple[int, bytes, str]:
    r = await client.get(url, timeout=HTTP_TIMEOUT)
    content = r.content if len(r.content) <= max_bytes else r.content[:max_bytes]
    return r.status_code, content, r.headers.get("content-type", "")


def _is_pdf(url: str, content_type: str, content: bytes) -> bool:
    if "application/pdf" in content_type.lower():
        return True
    if urlparse(url).path.lower().endswith(".pdf"):
        return True
    return content[:4] == b"%PDF"


async def find_and_fetch_menu(
    client: httpx.AsyncClient, website: str
) -> tuple[str, str, bytes] | None:
    parsed = urlparse(website)
    origin = f"{parsed.scheme or 'https'}://{parsed.netloc or parsed.path}"
    for path in MENU_PATHS:
        url = urljoin(origin, path)
        try:
            max_bytes = MAX_PDF_BYTES if path.endswith(".pdf") else MAX_HTML_BYTES
            status, content, ct = await _fetch(client, url, max_bytes)
        except Exception:
            continue
        if 200 <= status < 300 and content:
            kind = "pdf" if _is_pdf(url, ct, content) else "html"
            return url, kind, content

    try:
        status, content, ct = await _fetch(client, website, MAX_HTML_BYTES)
    except Exception:
        return None
    if not (200 <= status < 300 and content):
        return None

    if not _is_pdf(website, ct, content):
        try:
            html = content.decode("utf-8", errors="replace")
            for link in find_menu_links_in_html(html, website):
                try:
                    is_pdf_hint = link.lower().endswith(".pdf")
                    max_bytes = MAX_PDF_BYTES if is_pdf_hint else MAX_HTML_BYTES
                    s2, c2, ct2 = await _fetch(client, link, max_bytes)
                except Exception:
                    continue
                if 200 <= s2 < 300 and c2:
                    kind = "pdf" if _is_pdf(link, ct2, c2) else "html"
                    return link, kind, c2
        except Exception:
            pass

    return website, "pdf" if _is_pdf(website, ct, content) else "html", content


async def process_restaurant(
    rid: str,
    name: str,
    website: str,
    http_client: httpx.AsyncClient,
    stats: Stats,
) -> dict[str, Any]:
    log: dict[str, Any] = {
        "restaurant_id": rid,
        "url": website,
        "status": "unknown",
        "items_extracted": 0,
        "error_message": None,
        "_items": [],
    }
    try:
        if not await check_robots(http_client, website):
            log["status"] = "robots_blocked"
            stats.robots_blocked += 1
            return log

        found = await find_and_fetch_menu(http_client, website)
        if not found:
            log["status"] = "no_menu_found"
            stats.no_menu += 1
            return log
        url, kind, content = found
        log["url"] = url

        if kind == "html":
            cleaned = clean_html_text(content.decode("utf-8", errors="replace"))
            log["_debug_cleaned_len"] = len(cleaned)
            log["_debug_kind"] = "html"
            if len(cleaned) < 100:
                log["status"] = "no_menu_found"
                log["error_message"] = f"cleaned_html_too_short({len(cleaned)})"
                stats.no_menu += 1
                return log
            extracted = await gemini_text_call(cleaned)
            stats.gemini_calls += 1
            log["_debug_gemini_items"] = len(extracted.items)
            log["_debug_warnings"] = extracted.warnings
        else:
            pdf_text = pdf_to_text(content)
            if len(pdf_text) >= 300:
                extracted = await gemini_text_call(pdf_text)
                stats.gemini_calls += 1
            else:
                imgs = pdf_to_images(content)
                if not imgs:
                    log["status"] = "no_menu_found"
                    stats.no_menu += 1
                    return log
                extracted = await gemini_vision_call(imgs)
                stats.gemini_calls += 1

        valid = [
            it
            for it in extracted.items
            if it.name and it.name.strip() and 0 < it.price_cents <= MAX_PRICE_CENTS
        ]
        log["items_extracted"] = len(valid)
        if not valid:
            log["status"] = "no_menu_found"
            stats.no_menu += 1
            return log

        log["status"] = "success"
        stats.success += 1
        stats.items_saved += len(valid)
        log["_items"] = [
            {
                "name": it.name.strip()[:255],
                "description": (it.description or None),
                "price_cents": int(it.price_cents),
                "category": (it.category or "other")[:50],
            }
            for it in valid
        ]
        return log
    except httpx.HTTPError as e:
        log["status"] = "http_error"
        log["error_message"] = f"{type(e).__name__}: {str(e)[:200]}"
        stats.http_error += 1
        return log
    except Exception as e:
        log["status"] = "parse_failed"
        log["error_message"] = f"{type(e).__name__}: {str(e)[:200]}"
        stats.parse_failed += 1
        stats.gemini_errors += 1
        return log


async def persist_result(log: dict[str, Any]) -> None:
    rid_uuid = UUID(log["restaurant_id"])
    items = log.get("_items") or []
    async with SessionLocal() as db:
        async with db.begin():
            db.add(
                CrawlLog(
                    restaurant_id=rid_uuid,
                    url=log["url"],
                    status=log["status"],
                    items_extracted=log["items_extracted"],
                    error_message=log["error_message"],
                )
            )
            for it in items:
                db.add(
                    MenuItem(
                        restaurant_id=rid_uuid,
                        name=it["name"],
                        description=it["description"],
                        price_cents=it["price_cents"],
                        category=it["category"],
                        source="gemini_web",
                    )
                )


async def load_done_set(db: AsyncSession) -> set[str]:
    result = await db.execute(
        text(
            "SELECT restaurant_id::text FROM crawl_log "
            "WHERE status IN ('success', 'no_menu_found', 'robots_blocked')"
        )
    )
    return {row[0] for row in result if row[0]}


async def load_failed_ids(db: AsyncSession) -> set[str]:
    result = await db.execute(
        text(
            "SELECT DISTINCT restaurant_id::text FROM crawl_log "
            "WHERE status='parse_failed'"
        )
    )
    return {row[0] for row in result if row[0]}


async def load_targets(db: AsyncSession) -> list[tuple[str, str, str]]:
    rows = (
        await db.execute(
            text(
                "SELECT id::text, name, website FROM restaurants "
                "WHERE website IS NOT NULL "
                "AND google_place_id NOT LIKE 'osm_%' "
                "ORDER BY id"
            )
        )
    ).all()
    return [(r[0], r[1], r[2]) for r in rows]


async def run(args: argparse.Namespace) -> None:
    stats = Stats()
    async with SessionLocal() as bootstrap:
        if args.fresh and not args.dry_run:
            print("[fresh] TRUNCATE crawl_log + DELETE menu_items WHERE source='gemini_web'")
            await bootstrap.execute(text("TRUNCATE crawl_log"))
            await bootstrap.execute(text("DELETE FROM menu_items WHERE source='gemini_web'"))
            await bootstrap.commit()
        all_targets = await load_targets(bootstrap)
        if args.retry_failed:
            failed = await load_failed_ids(bootstrap)
            targets = [t for t in all_targets if t[0] in failed]
            done = set()
        else:
            done = set() if args.fresh else await load_done_set(bootstrap)
            targets = [t for t in all_targets if t[0] not in done]

    if args.limit:
        targets = targets[: args.limit]

    print(
        f"[start] {len(targets)} targets (pool={len(all_targets)}, already_done={len(done)}) "
        f"concurrency={CONCURRENCY} dry_run={args.dry_run}",
        flush=True,
    )

    sem = asyncio.Semaphore(CONCURRENCY)

    async def progress_loop() -> None:
        while True:
            await asyncio.sleep(60)
            elapsed = time.time() - stats.start_t
            done_n = (
                stats.success + stats.no_menu + stats.robots_blocked
                + stats.http_error + stats.parse_failed
            )
            rate = done_n / elapsed if elapsed else 0.0
            remaining = len(targets) - done_n
            eta = f"~{remaining / rate / 60:.1f}m" if rate > 0 else "?"
            mm, ss = divmod(int(elapsed), 60)
            print(
                f"[{mm:02d}:{ss:02d}] done={done_n}/{len(targets)} "
                f"success={stats.success} items={stats.items_saved} "
                f"no_menu={stats.no_menu} http_err={stats.http_error} "
                f"robots={stats.robots_blocked} parse_err={stats.parse_failed} "
                f"eta={eta}",
                flush=True,
            )

    async def worker(rid: str, name: str, website: str, http_client: httpx.AsyncClient) -> None:
        async with sem:
            stats.attempted += 1
            log = await process_restaurant(rid, name, website, http_client, stats)
            status = log["status"]
            n = log["items_extracted"]
            print(
                f"[{stats.attempted:>4}/{len(targets)}] {status:<14} items={n:<3} "
                f"{name[:45]:<45} -> {log['url'][:60]}",
                flush=True,
            )
            if log.get("error_message"):
                print(f"    ! {log['error_message']}", flush=True)
            if args.dry_run:
                dbg_len = log.get("_debug_cleaned_len")
                dbg_items = log.get("_debug_gemini_items")
                dbg_warn = log.get("_debug_warnings")
                if dbg_len is not None:
                    print(
                        f"    debug: cleaned_len={dbg_len} "
                        f"gemini_items={dbg_items} warnings={dbg_warn}",
                        flush=True,
                    )
            items = log.get("_items") or []
            if args.dry_run:
                for it in items[:3]:
                    print(
                        f"    - ${it['price_cents'] / 100:>6.2f}  "
                        f"{it['name'][:60]}  ({it['category']})"
                    )
                if len(items) > 3:
                    print(f"    ... +{len(items) - 3} more items")
            else:
                try:
                    await persist_result(log)
                except Exception as e:
                    print(f"    [persist-error] {type(e).__name__}: {str(e)[:200]}")
            await asyncio.sleep(PER_RESTAURANT_SLEEP_S)

    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf,*/*"}
    async with httpx.AsyncClient(
        headers=headers,
        timeout=httpx.Timeout(HTTP_TIMEOUT),
        follow_redirects=True,
    ) as http_client:
        progress_task: asyncio.Task[None] | None = None
        if not args.dry_run and len(targets) > 5:
            progress_task = asyncio.create_task(progress_loop())
        try:
            await asyncio.gather(
                *(worker(rid, name, web, http_client) for rid, name, web in targets),
                return_exceptions=True,
            )
        finally:
            if progress_task:
                progress_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await progress_task

    _print_report(stats, len(targets))
    await engine.dispose()


def _print_report(stats: Stats, n_targets: int) -> None:
    elapsed = time.time() - stats.start_t
    print("\n" + "=" * 72)
    print(" Task 1.4 - crawl + parse report")
    print("=" * 72)
    print(f"  Elapsed:            {elapsed:.1f}s")
    print(f"  Restaurants:        {stats.attempted}/{n_targets}")
    print(f"  Success:            {stats.success}")
    print(f"  Menu items saved:   {stats.items_saved}")
    print(f"  No menu found:      {stats.no_menu}")
    print(f"  Robots blocked:     {stats.robots_blocked}")
    print(f"  HTTP errors:        {stats.http_error}")
    print(f"  Parse failed:       {stats.parse_failed}")
    print(f"  Gemini calls:       {stats.gemini_calls} (errors {stats.gemini_errors})")
    est_in = stats.gemini_calls * 30_000
    est_out = stats.gemini_calls * 1_500
    est = (est_in / 1_000_000) * 0.075 + (est_out / 1_000_000) * 0.30
    print(f"  Gemini est. cost:   ${est:.3f}  (rough, assumes ~30k in / 1.5k out per call)")
    print("=" * 72)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Task 1.4 web crawl + Gemini parse")
    p.add_argument("--dry-run", action="store_true", help="First 5 restaurants, no DB writes")
    p.add_argument("--retry-failed", action="store_true", help="Only retry status='parse_failed'")
    p.add_argument(
        "--fresh",
        action="store_true",
        help="Truncate crawl_log + delete menu_items WHERE source='gemini_web'",
    )
    p.add_argument("--limit", type=int, default=None, help="Cap target count")
    return p.parse_args()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    args = parse_args()
    if args.dry_run and args.limit is None:
        args.limit = 5
    asyncio.run(run(args))
