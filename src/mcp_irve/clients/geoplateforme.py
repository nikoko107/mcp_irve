"""Client pour l'API Géoplateforme IGN — réseau routier BD TOPO® (WFS) et calcul
d'itinéraire (data.geopf.fr).

Vérifié en direct :
- Le type WFS des tronçons routiers est ``BDTOPO_V3:troncon_de_route``, servi sous
  ``https://data.geopf.fr/wfs/ows``. Les géométries renvoyées sont 3D (Z = altitude) —
  on les aplatit en 2D avant toute opération shapely.
- **Piège d'ordre des axes** : bien que EPSG:4326 impose nominalement l'ordre
  (latitude, longitude), ce service n'accepte le filtre ``BBOX`` qu'en ordre
  (longitude, latitude) avec le suffixe explicite ``,EPSG:4326`` — l'ordre
  (latitude, longitude) renvoie silencieusement zéro résultat.
- L'identifiant stable du tronçon est l'attribut ``cleabs``, la nature (route/chemin...)
  est l'attribut ``nature``.
- L'API itinéraire (``/navigation/itineraire``) est accessible sans clé ; elle est
  limitée à 5 req/s/IP (voir ``clients.http.itineraire_rate_limiter``) ; la réponse
  contient ``distance`` (m), ``duration`` (s) et une ``geometry`` GeoJSON en WGS84.
"""

from __future__ import annotations

import httpx
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform

from ..config import SETTINGS
from ..errors import ExternalApiError
from ..geo.projections import l93_to_wgs84, reproject_wgs84_to_l93, wgs84_to_l93
from ..models import Itineraire, RouteSegment
from .http import itineraire_rate_limiter


def _drop_z(geometry: BaseGeometry) -> BaseGeometry:
    """Aplatit une géométrie 3D en 2D (ignore l'altitude)."""
    return shapely_transform(lambda x, y, z=None: (x, y), geometry)


def _bbox_wgs84(lat: float, lon: float, rayon_m: float) -> tuple[float, float, float, float]:
    """Bbox carrée de +/- rayon_m autour du point, calculée en Lambert 93 (donc
    exacte en mètres) puis reprojetée en WGS84 pour le filtre WFS."""
    x, y = wgs84_to_l93(lat, lon)
    lat1, lon1 = l93_to_wgs84(x - rayon_m, y - rayon_m)
    lat2, lon2 = l93_to_wgs84(x + rayon_m, y + rayon_m)
    return (min(lon1, lon2), min(lat1, lat2), max(lon1, lon2), max(lat1, lat2))


async def recuperer_routes(
    client: httpx.AsyncClient, lat: float, lon: float, rayon_m: int
) -> list[RouteSegment]:
    min_lon, min_lat, max_lon, max_lat = _bbox_wgs84(lat, lon, rayon_m)
    try:
        response = await client.get(
            f"{SETTINGS.geopf_wfs_url}/ows",
            params={
                "SERVICE": "WFS",
                "VERSION": "2.0.0",
                "REQUEST": "GetFeature",
                "TYPENAMES": SETTINGS.geopf_wfs_typename,
                "SRSNAME": "EPSG:4326",
                "BBOX": f"{min_lon},{min_lat},{max_lon},{max_lat},EPSG:4326",
                "OUTPUTFORMAT": "application/json",
                "COUNT": 1000,
            },
            timeout=SETTINGS.http_timeout_s,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ExternalApiError(f"Échec de l'appel WFS BD TOPO® (routes) : {exc}") from exc

    data = response.json()
    segments: list[RouteSegment] = []
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        geom_wgs84 = _drop_z(shape(feature["geometry"]))
        segments.append(
            RouteSegment(
                id=props.get("cleabs") or feature.get("id") or f"route-{len(segments)}",
                nature=props.get("nature", "inconnue"),
                geometry=reproject_wgs84_to_l93(geom_wgs84),
                attributes=props,
            )
        )
    return segments


async def calculer_itineraire(
    client: httpx.AsyncClient,
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
) -> Itineraire:
    await itineraire_rate_limiter.acquire()
    try:
        response = await client.get(
            SETTINGS.geopf_itineraire_url,
            params={
                "resource": SETTINGS.geopf_itineraire_resource,
                "start": f"{start_lon},{start_lat}",
                "end": f"{end_lon},{end_lat}",
                "profile": SETTINGS.geopf_itineraire_profile,
                "optimization": SETTINGS.geopf_itineraire_optimization,
                "geometryFormat": "geojson",
            },
            timeout=SETTINGS.http_timeout_s,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ExternalApiError(f"Échec de l'appel itinéraire IGN Géoplateforme : {exc}") from exc

    data = response.json()
    geometry = None
    if data.get("geometry"):
        geometry = reproject_wgs84_to_l93(shape(data["geometry"]))
    return Itineraire(
        distance_m=data["distance"],
        duree_s=data.get("duration"),
        geometry=geometry,
    )
