"""Export GeoJSON (outil exporter_geojson).

RFC 7946 impose des coordonnées WGS84 quel que soit le CRS de travail interne — la
reprojection est faite par ``outputs._shared.construire_features``. Pour
``niveau="complet"``, toutes les couches sont regroupées dans une unique
FeatureCollection avec une propriété ``layer`` par feature (plutôt que plusieurs
fichiers), directement exploitable dans QGIS en stylant par attribut.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..state import SessionState
from ._shared import construire_features, new_output_path


def exporter_geojson(state: SessionState, niveau: str = "resultat") -> Path:
    features = construire_features(state, niveau)
    collection = {"type": "FeatureCollection", "features": features}
    chemin = new_output_path(f"geojson_{niveau}", "geojson")
    chemin.write_text(json.dumps(collection, ensure_ascii=False, indent=2))
    return chemin
