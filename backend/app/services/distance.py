"""Haversine distance + bounding-box helpers (PostGIS Plan B)."""

from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_000
_METERS_PER_DEGREE_LAT = 111_320.0
# Small safety margin: the simple 111.32 km/degree approximation can be a few
# meters short at the N/S edges. We inflate the pre-filter box slightly so no
# in-range restaurant can slip through the bounding box; exact haversine is
# applied afterwards to trim the extras.
_BBOX_SAFETY_MARGIN = 1.01


def haversine_distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two coordinates, in meters."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bounding_box(
    lat: float, lng: float, radius_m: float
) -> tuple[float, float, float, float]:
    """Pre-filter box for lat/lng index. Returns (lat_min, lat_max, lng_min, lng_max).

    Slightly over-includes near poles — we filter exactly via haversine after.
    """
    padded = radius_m * _BBOX_SAFETY_MARGIN
    lat_delta = padded / _METERS_PER_DEGREE_LAT
    cos_lat = math.cos(math.radians(lat))
    # Guard against division-by-zero at the poles; GR is nowhere near so this is a
    # belt-and-suspenders safeguard.
    if abs(cos_lat) < 1e-9:
        lng_delta = 180.0
    else:
        lng_delta = padded / (_METERS_PER_DEGREE_LAT * cos_lat)
    return (lat - lat_delta, lat + lat_delta, lng - lng_delta, lng + lng_delta)
