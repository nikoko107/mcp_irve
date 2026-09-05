"""Utilitaires communs aux modules de sortie (carte, export GeoJSON) : nommage des
fichiers générés et construction des features GeoJSON (toujours en WGS84, conformément
à RFC 7946) à partir de l'état de session.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry

from ..config import SETTINGS
from ..geo.projections import reproject_l93_to_wgs84
from ..state import SessionState


def new_output_path(prefix: str, ext: str) -> Path:
    SETTINGS.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    return SETTINGS.output_dir / f"{prefix}_{timestamp}_{suffix}.{ext}"


def _feature(geometry_l93: BaseGeometry, layer: str, properties: dict | None = None) -> dict:
    geom_wgs84 = reproject_l93_to_wgs84(geometry_l93)
    return {
        "type": "Feature",
        "geometry": mapping(geom_wgs84),
        "properties": {"layer": layer, **(properties or {})},
    }


def _point_feature(lat: float, lon: float, layer: str, properties: dict | None = None) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {"layer": layer, **(properties or {})},
    }


def construire_features(
    state: SessionState, niveau: str, *, inclure_reseau_bt: bool = True
) -> list[dict]:
    """Construit la liste de features GeoJSON (WGS84) pour l'état courant.

    ``niveau="resultat"`` : point de départ, tronçon retenu, point de raccordement,
    itinéraire routier. ``niveau="complet"`` : ajoute en plus l'intégralité des couches
    réseau routier / candidats utilisées par l'analyse (+ réseau BT si
    ``inclure_reseau_bt``, désactivé par la carte HTML qui affiche ce réseau en direct
    depuis l'API Enedis plutôt que le figer au moment de l'analyse — voir outputs/map.py).
    """
    features: list[dict] = []

    if state.point_depart is not None:
        features.append(
            _point_feature(
                state.point_depart.lat,
                state.point_depart.lon,
                "depart",
                {"adresse": state.adresse_normalisee},
            )
        )

    if niveau == "complet":
        if state.buffer_zone is not None:
            features.append(
                _feature(state.buffer_zone, "buffer", {"buffer_m": state.buffer_m})
            )
        if inclure_reseau_bt:
            for seg in state.reseau_bt:
                features.append(_feature(seg.geometry, f"bt_{seg.type}", {"id": seg.id}))
        for seg in state.reseau_routier:
            features.append(
                _feature(seg.geometry, "routes", {"id": seg.id, "nature": seg.nature})
            )
        for cand in state.candidats:
            features.append(
                _feature(
                    cand.geometry,
                    "candidats",
                    {"id": cand.candidate_id, "type": cand.type},
                )
            )

    if state.resultat is not None:
        resultat = state.resultat
        features.append(
            _feature(
                resultat.candidat.geometry,
                "resultat",
                {
                    "troncon_id": resultat.troncon_id,
                    "type": resultat.type,
                    "distance_vol_oiseau_m": round(resultat.distance_vol_oiseau_m, 1),
                    "distance_routiere_m": round(resultat.distance_routiere_m, 1),
                    "eligible": resultat.eligible,
                },
            )
        )
        features.append(
            _point_feature(
                resultat.point_raccordement.lat,
                resultat.point_raccordement.lon,
                "point_raccordement",
            )
        )
        if resultat.itineraire is not None and resultat.itineraire.geometry is not None:
            features.append(
                _feature(
                    resultat.itineraire.geometry,
                    "itineraire",
                    {
                        "distance_m": round(resultat.itineraire.distance_m, 1),
                        "repartition_type_m": {
                            k: round(v, 1) for k, v in resultat.repartition_type_m.items()
                        },
                    },
                )
            )

    return features
