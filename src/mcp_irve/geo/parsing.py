"""Détection et parsing de la saisie utilisateur (outil geocoder_entree).

Google Maps propose, au clic droit sur un point, de copier ses coordonnées au format
"lat, lon" en degrés décimaux (ex. "48.8566, 2.3522"). On détecte ce format pour
éviter un aller-retour de géocodage inutile — toute autre saisie est traitée comme
une adresse texte à envoyer à l'API BAN.
"""

from __future__ import annotations

import re

_COORD_RE = re.compile(r"^\s*(?P<lat>-?\d{1,3}(?:\.\d+)?)\s*,\s*(?P<lon>-?\d{1,3}(?:\.\d+)?)\s*$")


def detect_saisie_type(saisie: str) -> str:
    """Retourne "coordonnees" ou "adresse"."""
    return "coordonnees" if _COORD_RE.match(saisie) else "adresse"


def parse_coordonnees(saisie: str) -> tuple[float, float]:
    """Parse une saisie "lat, lon" en (lat, lon).

    Lève ValueError si le format ne correspond pas ou si les valeurs sont hors des
    bornes valides (latitude ∈ [-90, 90], longitude ∈ [-180, 180]).
    """
    match = _COORD_RE.match(saisie)
    if not match:
        raise ValueError(f"Saisie non reconnue comme des coordonnées : {saisie!r}")
    lat = float(match.group("lat"))
    lon = float(match.group("lon"))
    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"Latitude hors bornes [-90, 90] : {lat}")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError(f"Longitude hors bornes [-180, 180] : {lon}")
    return lat, lon
