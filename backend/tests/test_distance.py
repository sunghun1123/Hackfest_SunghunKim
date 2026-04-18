"""Unit tests for the PostGIS Plan B fallback math."""

import math

from app.services.distance import bounding_box, haversine_distance_m


def test_haversine_zero_distance():
    assert haversine_distance_m(42.96, -85.66, 42.96, -85.66) == 0.0


def test_haversine_one_degree_latitude_approx_111km():
    # 1 degree of latitude ~= 111.32 km anywhere on Earth.
    d = haversine_distance_m(0.0, 0.0, 1.0, 0.0)
    assert 110_000 < d < 112_000


def test_haversine_known_gr_pair():
    # Two points roughly ~2km apart in Grand Rapids.
    a = (42.9634, -85.6681)
    b = (42.9812, -85.6681)  # ~2 km north
    d = haversine_distance_m(*a, *b)
    assert 1800 < d < 2200


def test_haversine_symmetric():
    d1 = haversine_distance_m(42.96, -85.66, 43.05, -85.55)
    d2 = haversine_distance_m(43.05, -85.55, 42.96, -85.66)
    assert math.isclose(d1, d2, rel_tol=1e-9)


def test_bounding_box_covers_radius():
    lat, lng = 42.96, -85.66
    radius = 2000
    lat_min, lat_max, lng_min, lng_max = bounding_box(lat, lng, radius)
    # All four edges should be at least `radius` meters away.
    assert haversine_distance_m(lat, lng, lat_min, lng) >= radius - 1
    assert haversine_distance_m(lat, lng, lat_max, lng) >= radius - 1
    assert haversine_distance_m(lat, lng, lat, lng_min) >= radius - 1
    assert haversine_distance_m(lat, lng, lat, lng_max) >= radius - 1


def test_bounding_box_is_not_wildly_oversized():
    # Box diagonal should be within ~2x of the radius (sqrt(2) ish).
    lat, lng = 42.96, -85.66
    radius = 2000
    lat_min, lat_max, lng_min, lng_max = bounding_box(lat, lng, radius)
    corner_dist = haversine_distance_m(lat, lng, lat_max, lng_max)
    assert corner_dist < radius * 2
