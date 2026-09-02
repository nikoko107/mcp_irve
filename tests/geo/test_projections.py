from pytest import approx
from shapely.geometry import LineString, Point

from mcp_irve.geo.projections import (
    l93_to_wgs84,
    reproject_l93_to_wgs84,
    reproject_wgs84_to_l93,
    to_point_geo,
    wgs84_to_l93,
)

# Tour Eiffel, coordonnées WGS84 de référence.
TOUR_EIFFEL_LAT = 48.8584
TOUR_EIFFEL_LON = 2.2945


def test_wgs84_to_l93_roundtrip_returns_original_coordinates():
    x, y = wgs84_to_l93(TOUR_EIFFEL_LAT, TOUR_EIFFEL_LON)
    lat, lon = l93_to_wgs84(x, y)

    assert lat == approx(TOUR_EIFFEL_LAT, abs=1e-6)
    assert lon == approx(TOUR_EIFFEL_LON, abs=1e-6)


def test_wgs84_to_l93_gives_coordinates_in_expected_range_for_metropolitan_france():
    x, y = wgs84_to_l93(TOUR_EIFFEL_LAT, TOUR_EIFFEL_LON)

    assert 100_000 < x < 1_200_000
    assert 6_000_000 < y < 7_100_000


def test_to_point_geo_populates_both_crs():
    point = to_point_geo(TOUR_EIFFEL_LAT, TOUR_EIFFEL_LON)

    assert point.lat == TOUR_EIFFEL_LAT
    assert point.lon == TOUR_EIFFEL_LON
    x, y = wgs84_to_l93(TOUR_EIFFEL_LAT, TOUR_EIFFEL_LON)
    assert point.x_l93 == approx(x)
    assert point.y_l93 == approx(y)


def test_reproject_wgs84_to_l93_then_back_preserves_point():
    original = Point(TOUR_EIFFEL_LON, TOUR_EIFFEL_LAT)  # shapely: (x=lon, y=lat) en WGS84

    reprojected = reproject_wgs84_to_l93(original)
    back = reproject_l93_to_wgs84(reprojected)

    assert back.x == approx(original.x, abs=1e-6)
    assert back.y == approx(original.y, abs=1e-6)


def test_reproject_wgs84_to_l93_handles_linestring():
    line = LineString([(2.2945, 48.8584), (2.3522, 48.8566)])

    reprojected = reproject_wgs84_to_l93(line)

    assert reprojected.geom_type == "LineString"
    assert len(reprojected.coords) == 2
    for x, y in reprojected.coords:
        assert 100_000 < x < 1_200_000
        assert 6_000_000 < y < 7_100_000
