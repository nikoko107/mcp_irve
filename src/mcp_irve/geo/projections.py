"""Reprojections WGS84 (échange) <-> Lambert 93 / EPSG:2154 (calcul).

Les ``pyproj.Transformer`` sont coûteux à construire — on les met en cache au niveau
module puisqu'ils sont réutilisés à chaque appel d'outil.
"""

from __future__ import annotations

from functools import lru_cache

from pyproj import Transformer
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

from ..config import SETTINGS
from ..models import PointGeo


@lru_cache(maxsize=4)
def _transformer(from_crs: str, to_crs: str) -> Transformer:
    return Transformer.from_crs(from_crs, to_crs, always_xy=True)


def wgs84_to_l93(lat: float, lon: float) -> tuple[float, float]:
    """(lat, lon) WGS84 -> (x, y) Lambert 93."""
    x, y = _transformer(SETTINGS.crs_echange, SETTINGS.crs_travail).transform(lon, lat)
    return x, y


def l93_to_wgs84(x: float, y: float) -> tuple[float, float]:
    """(x, y) Lambert 93 -> (lat, lon) WGS84."""
    lon, lat = _transformer(SETTINGS.crs_travail, SETTINGS.crs_echange).transform(x, y)
    return lat, lon


def to_point_geo(lat: float, lon: float) -> PointGeo:
    x, y = wgs84_to_l93(lat, lon)
    return PointGeo(lat=lat, lon=lon, x_l93=x, y_l93=y)


def reproject_wgs84_to_l93(geometry: BaseGeometry) -> BaseGeometry:
    return transform(_transformer(SETTINGS.crs_echange, SETTINGS.crs_travail).transform, geometry)


def reproject_l93_to_wgs84(geometry: BaseGeometry) -> BaseGeometry:
    return transform(_transformer(SETTINGS.crs_travail, SETTINGS.crs_echange).transform, geometry)
