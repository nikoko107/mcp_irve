"""Client pour l'open data Enedis (réseau BT aérien + souterrain) — opendata.enedis.fr,
API Explore v2.1 (Opendatasoft).

Vérifié en direct :
- Les deux jeux de données existent bien sous ces noms : ``reseau-bt`` (aérien) et
  ``reseau-souterrain-bt`` (souterrain).
- Le filtre géographique fonctionne via ODSQL ``within_distance(geometry, geom'POINT(lon
  lat)', <rayon>m)`` — le paramètre ``geofilter.distance`` hérité de l'API v1 est accepté
  syntaxiquement mais n'a AUCUN effet sur ce point d'accès v2.1 (il renvoie les mêmes
  résultats qu'une requête non filtrée) : ne pas l'utiliser.
- Le champ ``geometry`` de chaque enregistrement est une chaîne JSON (pas un objet GeoJSON
  imbriqué) qu'il faut parser explicitement.
- Aucun identifiant unique de tronçon n'est fourni par l'API — on en construit un stable
  pour la session (dataset + décalage de pagination).
"""

from __future__ import annotations

import json

import httpx
from shapely.geometry import shape

from ..config import SETTINGS
from ..errors import ExternalApiError
from ..geo.projections import reproject_wgs84_to_l93
from ..models import ReseauSegment


async def _fetch_dataset(
    client: httpx.AsyncClient,
    dataset: str,
    type_label: str,
    lat: float,
    lon: float,
    rayon_m: int,
) -> list[ReseauSegment]:
    segments: list[ReseauSegment] = []
    offset = 0
    where = f"within_distance(geometry, geom'POINT({lon} {lat})', {rayon_m}m)"

    while len(segments) < SETTINGS.enedis_max_records:
        try:
            response = await client.get(
                f"{SETTINGS.enedis_base_url}/{dataset}/records",
                params={"where": where, "limit": SETTINGS.enedis_page_size, "offset": offset},
                timeout=SETTINGS.http_timeout_s,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ExternalApiError(
                f"Échec de l'appel à l'open data Enedis ({dataset}) : {exc}"
            ) from exc

        data = response.json()
        results = data.get("results") or []
        if not results:
            break

        for i, record in enumerate(results):
            raw_geometry = record.get("geometry")
            if not raw_geometry:
                continue
            geom_dict = json.loads(raw_geometry) if isinstance(raw_geometry, str) else raw_geometry
            geom_l93 = reproject_wgs84_to_l93(shape(geom_dict))
            attributes = {k: v for k, v in record.items() if k != "geometry"}
            segments.append(
                ReseauSegment(
                    id=f"{dataset}-{offset + i}",
                    type=type_label,
                    geometry=geom_l93,
                    attributes=attributes,
                )
            )

        if len(results) < SETTINGS.enedis_page_size:
            break
        offset += SETTINGS.enedis_page_size

    return segments


async def recuperer_troncons(
    client: httpx.AsyncClient, lat: float, lon: float, rayon_m: int
) -> tuple[list[ReseauSegment], list[ReseauSegment]]:
    """Retourne (tronçons aériens, tronçons souterrains) dans le rayon donné autour du point."""
    aeriens = await _fetch_dataset(
        client, SETTINGS.enedis_dataset_aerien, "aerien", lat, lon, rayon_m
    )
    souterrains = await _fetch_dataset(
        client, SETTINGS.enedis_dataset_souterrain, "souterrain", lat, lon, rayon_m
    )
    return aeriens, souterrains
