"""Gemini-backed endpoints: photo menu parsing + NL recommendation.

  POST /parse-menu-image (multipart) — runs Gemini Vision on a user photo,
  returns structured items. Rate-limited per device (5/min) because each
  call hits paid API quota.

  POST /recommend (JSON) — geo-filter nearby active menus, ask Gemini to
  rank them against a free-text query, then enrich the returned IDs with
  their restaurant/price/distance for the Android client.

Both endpoints rely on `GeminiService` (Task 1.8) and its safe-default
behavior: if Gemini errors or returns garbage, callers still get a
well-formed empty response instead of a 500.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.schemas.gemini_responses import ParsedMenuResponse
from app.schemas.recommend import (
    RecommendedMenu,
    RecommendRequest,
    RecommendResponsePayload,
)
from app.services.devices import require_device_id
from app.services.distance import bounding_box, haversine_distance_m
from app.services.gemini import GeminiService
from app.services.rate_limit import photo_parse_limiter

router = APIRouter(tags=["gemini"])

_ALLOWED_IMAGE_MIME = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
_CANDIDATE_LIMIT = 50
_SEARCH_RADIUS_M = 2000

_gemini_service_singleton: GeminiService | None = None


def get_gemini_service() -> GeminiService:
    """FastAPI dep returning a process-wide GeminiService. Tests override
    this via `app.dependency_overrides[get_gemini_service]`."""
    global _gemini_service_singleton
    if _gemini_service_singleton is None:
        _gemini_service_singleton = GeminiService()
    return _gemini_service_singleton


# ---------------------------------------------------------------------------
# POST /parse-menu-image
# ---------------------------------------------------------------------------

@router.post("/parse-menu-image", response_model=ParsedMenuResponse)
async def parse_menu_image(
    image: UploadFile = File(...),
    device_id: str = Depends(require_device_id),
    svc: GeminiService = Depends(get_gemini_service),
) -> ParsedMenuResponse:
    if not photo_parse_limiter.check_and_record(device_id):
        raise HTTPException(
            status_code=429,
            detail={
                "error": {
                    "code": "RATE_LIMITED",
                    "message": "Too many photo-parse requests — limit is 5/min per device",
                    "details": {"window_seconds": 60, "max_calls": 5},
                }
            },
        )

    content_type = (image.content_type or "image/jpeg").lower()
    if content_type not in _ALLOWED_IMAGE_MIME:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "UNSUPPORTED_MEDIA_TYPE",
                    "message": f"Expected JPEG/PNG/WEBP image, got {content_type}",
                    "details": {},
                }
            },
        )

    data = await image.read()
    if not data:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "EMPTY_IMAGE",
                    "message": "Uploaded image is empty",
                    "details": {},
                }
            },
        )

    return await svc.parse_photo(data, mime_type=content_type)


# ---------------------------------------------------------------------------
# POST /recommend
# ---------------------------------------------------------------------------

async def _fetch_candidates(
    db: AsyncSession, lat: float, lng: float, radius_m: int
) -> list[dict]:
    """Nearby active menus (up to 50), ordered verified-first then by distance.
    Dual-path: PostGIS ST_DWithin when enabled, bbox + haversine otherwise."""
    params = {"lat": lat, "lng": lng, "radius_m": radius_m, "limit": _CANDIDATE_LIMIT}
    select_cols = """
        m.id AS menu_id, m.name AS menu_name, m.price_cents,
        m.category AS menu_category, m.verification_status,
        r.id AS restaurant_id, r.name AS restaurant_name,
        r.lat, r.lng
    """
    verified_rank_sql = (
        "CASE WHEN m.verification_status = 'human_verified' THEN 0 ELSE 1 END"
    )

    if settings.postgis_enabled:
        sql = f"""
            SELECT {select_cols},
                   ST_Distance(
                       r.location,
                       ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography
                   ) AS distance_m,
                   {verified_rank_sql} AS v_rank
            FROM menu_items m
            JOIN restaurants r ON r.id = m.restaurant_id
            WHERE m.is_active = TRUE
              AND ST_DWithin(
                  r.location,
                  ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
                  :radius_m
              )
            ORDER BY v_rank ASC, distance_m ASC
            LIMIT :limit
        """
        rows = (await db.execute(text(sql), params)).all()
        return [
            {
                "id": str(r.menu_id),
                "name": r.menu_name,
                "restaurant": r.restaurant_name,
                "restaurant_id": str(r.restaurant_id),
                "price_cents": r.price_cents,
                "category": r.menu_category,
                "distance_m": int(round(r.distance_m)),
                "verified": r.verification_status == "human_verified",
                "verification_status": r.verification_status,
            }
            for r in rows
        ]

    # Plan B: bbox pre-filter + Python haversine.
    lat_min, lat_max, lng_min, lng_max = bounding_box(lat, lng, radius_m)
    params.update(
        {"lat_min": lat_min, "lat_max": lat_max, "lng_min": lng_min, "lng_max": lng_max}
    )
    sql = f"""
        SELECT {select_cols}, {verified_rank_sql} AS v_rank
        FROM menu_items m
        JOIN restaurants r ON r.id = m.restaurant_id
        WHERE m.is_active = TRUE
          AND r.lat BETWEEN :lat_min AND :lat_max
          AND r.lng BETWEEN :lng_min AND :lng_max
    """
    rows = (await db.execute(text(sql), params)).all()
    enriched: list[tuple[int, float, dict]] = []
    for r in rows:
        dist = haversine_distance_m(lat, lng, r.lat, r.lng)
        if dist > radius_m:
            continue
        enriched.append(
            (
                r.v_rank,
                dist,
                {
                    "id": str(r.menu_id),
                    "name": r.menu_name,
                    "restaurant": r.restaurant_name,
                    "restaurant_id": str(r.restaurant_id),
                    "price_cents": r.price_cents,
                    "category": r.menu_category,
                    "distance_m": int(round(dist)),
                    "verified": r.verification_status == "human_verified",
                    "verification_status": r.verification_status,
                },
            )
        )
    enriched.sort(key=lambda t: (t[0], t[1]))
    return [d for _rank, _dist, d in enriched[:_CANDIDATE_LIMIT]]


@router.post("/recommend", response_model=RecommendResponsePayload)
async def recommend(
    body: RecommendRequest,
    db: AsyncSession = Depends(get_db),
    svc: GeminiService = Depends(get_gemini_service),
) -> RecommendResponsePayload:
    candidates = await _fetch_candidates(db, body.lat, body.lng, _SEARCH_RADIUS_M)
    if not candidates:
        return RecommendResponsePayload(recommendations=[])

    # Gemini only needs the fields relevant to ranking; we'll re-enrich from
    # our own candidate dict once it returns.
    gemini_menus = [
        {
            "id": c["id"],
            "name": c["name"],
            "restaurant": c["restaurant"],
            "price_cents": c["price_cents"],
            "category": c["category"],
            "distance_m": c["distance_m"],
            "verified": c["verified"],
        }
        for c in candidates
    ]

    raw = await svc.recommend(
        query=body.query,
        menus=gemini_menus,
        lat=body.lat,
        lng=body.lng,
    )

    by_id = {c["id"]: c for c in candidates}
    enriched: list[RecommendedMenu] = []
    for rec in raw.recommendations[: body.max_results]:
        c = by_id.get(rec.menu_item_id)
        if c is None:
            # Defense-in-depth: GeminiService already whitelists, but if a
            # race trimmed the candidate list we skip rather than 500.
            continue
        enriched.append(
            RecommendedMenu(
                restaurant_id=UUID(c["restaurant_id"]),
                restaurant_name=c["restaurant"],
                menu_item_id=UUID(c["id"]),
                menu_name=c["name"],
                price_cents=c["price_cents"],
                distance_m=c["distance_m"],
                verification_status=c["verification_status"],
                reason=rec.reason,
            )
        )

    return RecommendResponsePayload(recommendations=enriched)
