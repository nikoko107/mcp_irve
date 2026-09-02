"""Client pour l'API BAN (géocodage d'adresse) — api-adresse.data.gouv.fr.

Vérifié en direct : la réponse est une FeatureCollection GeoJSON dont chaque feature
porte, dans ``properties``, les coordonnées Lambert 93 déjà calculées (``x``, ``y``) en
plus des coordonnées WGS84 dans ``geometry.coordinates`` — on les utilise telles quelles
plutôt que de reprojeter nous-mêmes, l'API étant la source faisant autorité pour ce point.
"""

from __future__ import annotations

import httpx

from ..config import SETTINGS
from ..errors import GeocodingError
from ..models import PointGeo


async def geocoder_adresse(client: httpx.AsyncClient, saisie: str) -> tuple[PointGeo, str]:
    """Géocode une adresse texte. Retourne (point, adresse_normalisee).

    Lève GeocodingError si l'appel échoue ou si aucune adresse ne correspond.
    """
    try:
        response = await client.get(
            f"{SETTINGS.ban_base_url}/search/",
            params={"q": saisie, "limit": 1},
            timeout=SETTINGS.http_timeout_s,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise GeocodingError(f"Échec de l'appel à l'API BAN pour {saisie!r} : {exc}") from exc

    data = response.json()
    features = data.get("features") or []
    if not features:
        raise GeocodingError(f"Aucune adresse trouvée pour {saisie!r}.")

    feature = features[0]
    props = feature["properties"]
    lon, lat = feature["geometry"]["coordinates"]
    point = PointGeo(lat=lat, lon=lon, x_l93=props["x"], y_l93=props["y"])
    return point, props.get("label", saisie)
