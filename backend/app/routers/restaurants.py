"""GET /restaurants/nearby + GET /restaurants/{id}.

Uses PostGIS (ST_DWithin + ST_Distance) when available, otherwise falls back
to a bounding-box pre-filter + Python haversine (see services/distance.py).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.schemas.restaurant import (
    CheapestMenu,
    MenuByTier,
    MenuItemOut,
    NearbyResponse,
    NearbyRestaurant,
    RestaurantDetail,
)
from app.services.distance import bounding_box, haversine_distance_m

router = APIRouter(prefix="/restaurants", tags=["restaurants"])


def _menu_status_from_row(cheapest_id, cheapest_status: str | None) -> str:
    if cheapest_id is None:
        return "empty"
    if cheapest_status == "human_verified":
        return "populated_verified"
    return "populated_ai"


def _build_cheapest(row) -> CheapestMenu | None:
    if row.cheapest_menu_id is None:
        return None
    return CheapestMenu(
        id=row.cheapest_menu_id,
        name=row.cheapest_menu_name,
        price_cents=row.cheapest_price_cents,
        tier=row.cheapest_tier,
        verification_status=row.cheapest_verification_status,
    )


# Order so populated_verified (0) < populated_ai (1) < empty (2).
_MENU_STATUS_RANK_SQL = """
CASE
    WHEN m.id IS NULL THEN 2
    WHEN m.verification_status = 'human_verified' THEN 0
    ELSE 1
END
"""


@router.get("/nearby", response_model=NearbyResponse)
async def get_nearby(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    radius_m: int = Query(2000, ge=1, le=50_000),
    tier: str | None = Query(None, pattern="^(survive|cost_effective|luxury)$"),
    verified_only: bool = False,
    include_empty: bool = True,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> NearbyResponse:
    # Filter clauses are shared between Plan A and Plan B.
    where_extra: list[str] = []
    params: dict = {"lat": lat, "lng": lng, "radius_m": radius_m, "limit": limit}

    if not include_empty:
        where_extra.append("m.id IS NOT NULL")
    if verified_only:
        where_extra.append("m.verification_status = 'human_verified'")
    if tier is not None:
        where_extra.append("m.tier = :tier")
        params["tier"] = tier

    extra_sql = (" AND " + " AND ".join(where_extra)) if where_extra else ""

    lateral_sql = """
        LEFT JOIN LATERAL (
            SELECT id, name, price_cents, tier, verification_status
            FROM menu_items
            WHERE restaurant_id = r.id AND is_active = TRUE
            ORDER BY price_cents ASC
            LIMIT 1
        ) m ON TRUE
    """

    select_cols = """
        r.id, r.name, r.category, r.lat, r.lng,
        r.google_rating, r.app_rating,
        m.id   AS cheapest_menu_id,
        m.name AS cheapest_menu_name,
        m.price_cents AS cheapest_price_cents,
        m.tier AS cheapest_tier,
        m.verification_status AS cheapest_verification_status
    """

    if settings.postgis_enabled:
        # Plan A: PostGIS spatial filter + distance.
        sql = f"""
            SELECT
                {select_cols},
                ST_Distance(
                    r.location,
                    ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography
                ) AS distance_m,
                {_MENU_STATUS_RANK_SQL} AS status_rank
            FROM restaurants r
            {lateral_sql}
            WHERE ST_DWithin(
                r.location,
                ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
                :radius_m
            )
            {extra_sql}
            ORDER BY status_rank ASC, distance_m ASC
            LIMIT :limit
        """
        result = await db.execute(text(sql), params)
        rows = result.all()
        out = [
            NearbyRestaurant(
                id=r.id,
                name=r.name,
                category=r.category,
                lat=r.lat,
                lng=r.lng,
                distance_m=int(round(r.distance_m)),
                google_rating=float(r.google_rating) if r.google_rating is not None else None,
                app_rating=float(r.app_rating) if r.app_rating is not None else None,
                menu_status=_menu_status_from_row(
                    r.cheapest_menu_id, r.cheapest_verification_status
                ),
                cheapest_menu=_build_cheapest(r),
            )
            for r in rows
        ]
        return NearbyResponse(restaurants=out, count=len(out))

    # Plan B: bounding box + Python haversine.
    lat_min, lat_max, lng_min, lng_max = bounding_box(lat, lng, radius_m)
    params.update(
        {"lat_min": lat_min, "lat_max": lat_max, "lng_min": lng_min, "lng_max": lng_max}
    )
    sql = f"""
        SELECT {select_cols}
        FROM restaurants r
        {lateral_sql}
        WHERE r.lat BETWEEN :lat_min AND :lat_max
          AND r.lng BETWEEN :lng_min AND :lng_max
          {extra_sql}
    """
    result = await db.execute(text(sql), params)
    rows = result.all()

    enriched: list[tuple[int, float, object]] = []
    for r in rows:
        dist = haversine_distance_m(lat, lng, r.lat, r.lng)
        if dist > radius_m:
            continue
        status = _menu_status_from_row(r.cheapest_menu_id, r.cheapest_verification_status)
        rank = 0 if status == "populated_verified" else 1 if status == "populated_ai" else 2
        enriched.append((rank, dist, r))

    enriched.sort(key=lambda t: (t[0], t[1]))
    enriched = enriched[:limit]

    out = [
        NearbyRestaurant(
            id=r.id,
            name=r.name,
            category=r.category,
            lat=r.lat,
            lng=r.lng,
            distance_m=int(round(dist)),
            google_rating=float(r.google_rating) if r.google_rating is not None else None,
            app_rating=float(r.app_rating) if r.app_rating is not None else None,
            menu_status=_menu_status_from_row(
                r.cheapest_menu_id, r.cheapest_verification_status
            ),
            cheapest_menu=_build_cheapest(r),
        )
        for _rank, dist, r in enriched
    ]
    return NearbyResponse(restaurants=out, count=len(out))


@router.get("/{restaurant_id}", response_model=RestaurantDetail)
async def get_restaurant(
    restaurant_id: UUID, db: AsyncSession = Depends(get_db)
) -> RestaurantDetail:
    rest_row = (
        await db.execute(
            text(
                """
                SELECT id, name, address, phone, website, lat, lng,
                       google_rating, app_rating, rating_count, hours_json
                FROM restaurants
                WHERE id = :id
                """
            ),
            {"id": restaurant_id},
        )
    ).first()
    if rest_row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "RESTAURANT_NOT_FOUND",
                    "message": "Restaurant not found",
                    "details": {},
                }
            },
        )

    menu_rows = (
        await db.execute(
            text(
                """
                SELECT id, name, description, price_cents, tier,
                       photo_url, verification_status, confirmation_count,
                       source, last_verified_at
                FROM menu_items
                WHERE restaurant_id = :id AND is_active = TRUE
                ORDER BY tier ASC, price_cents ASC
                """
            ),
            {"id": restaurant_id},
        )
    ).all()

    grouped: dict[str, list[MenuItemOut]] = {
        "survive": [],
        "cost_effective": [],
        "luxury": [],
    }
    for m in menu_rows:
        item = MenuItemOut(
            id=m.id,
            name=m.name,
            description=m.description,
            price_cents=m.price_cents,
            photo_url=m.photo_url,
            verification_status=m.verification_status,
            confirmation_count=m.confirmation_count,
            source=m.source,
            last_verified_at=m.last_verified_at,
        )
        if m.tier in grouped:
            grouped[m.tier].append(item)

    return RestaurantDetail(
        id=rest_row.id,
        name=rest_row.name,
        address=rest_row.address,
        phone=rest_row.phone,
        website=rest_row.website,
        lat=rest_row.lat,
        lng=rest_row.lng,
        google_rating=float(rest_row.google_rating) if rest_row.google_rating is not None else None,
        app_rating=float(rest_row.app_rating) if rest_row.app_rating is not None else None,
        rating_count=rest_row.rating_count,
        hours=rest_row.hours_json,
        menu=MenuByTier(**grouped),
    )
