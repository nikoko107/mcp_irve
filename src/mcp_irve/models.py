"""Structures de données internes du pipeline.

Toutes les géométries sont des objets ``shapely`` exprimés dans le CRS de travail
(Lambert 93 / EPSG:2154), sauf mention contraire. La reprojection vers WGS84 n'a
lieu qu'au moment des échanges avec le client MCP ou des exports fichiers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shapely.geometry.base import BaseGeometry


@dataclass(frozen=True)
class PointGeo:
    """Un point exprimé simultanément en WGS84 (échange) et Lambert 93 (calcul)."""

    lat: float
    lon: float
    x_l93: float
    y_l93: float


@dataclass
class ReseauSegment:
    """Tronçon du réseau BT Enedis (aérien ou souterrain)."""

    id: str
    type: str  # "aerien" | "souterrain"
    geometry: BaseGeometry  # LineString, EPSG:2154
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class RouteSegment:
    """Tronçon du réseau routier BD TOPO®."""

    id: str
    nature: str  # attribut "nature" BD TOPO (ex. "Route à 1 chaussée", "Chemin")
    geometry: BaseGeometry  # LineString, EPSG:2154
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class CandidateSegment:
    """Portion d'un tronçon routier retenue par le filtrage d'accessibilité, i.e.
    incluse dans le buffer autour du réseau BT (voir geo.accessibility.filtrer_candidats).
    """

    candidate_id: str
    source_troncon_id: str
    type: str  # nature du tronçon routier d'origine
    geometry: BaseGeometry  # LineString, portion dans le buffer, EPSG:2154
    source_geometry: BaseGeometry  # géométrie complète du tronçon routier d'origine
    length_m: float  # longueur de la portion candidate (pas du tronçon complet)


@dataclass
class RankedCandidate:
    """Un candidat classé par distance à vol d'oiseau, avant/après calcul d'itinéraire."""

    candidate: CandidateSegment
    point_le_plus_proche: BaseGeometry  # Point, EPSG:2154 — projection du point de départ
    distance_vol_oiseau_m: float
    distance_routiere_m: float | None = None


@dataclass
class Itineraire:
    """Résultat d'un calcul d'itinéraire IGN Géoplateforme."""

    distance_m: float
    duree_s: float | None
    geometry: BaseGeometry | None  # LineString, EPSG:2154


@dataclass
class Resultat:
    """Résultat final du pipeline, tel que renvoyé par selectionner_meilleur_candidat
    et consommé par les outils de génération de sorties (carte, GeoJSON, PDF).
    """

    troncon_id: str
    type: str
    distance_vol_oiseau_m: float
    distance_routiere_m: float
    point_raccordement: PointGeo
    eligible: bool
    candidat: CandidateSegment
    itineraire: Itineraire | None = None
    repartition_type_m: dict[str, float] = field(default_factory=dict)
    """Longueur de l'itinéraire (mètres) par nature de voie traversée — voir
    geo/itineraire.py::repartir_longueur_par_type. Vide si l'itinéraire n'a pas de
    géométrie exploitable."""
