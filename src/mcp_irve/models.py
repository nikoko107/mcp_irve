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
    """Distance totale départ -> réseau BT une fois calculée : premier tronçon (départ ->
    point réellement pris comme origine par l'itinéraire IGN, voir distance_premier_troncon_m)
    + itinéraire piéton (-> point_le_plus_proche) + dernier tronçon (point_le_plus_proche ->
    câble BT, voir distance_dernier_troncon_m). C'est cette distance totale qui sert au
    classement du meilleur candidat et à la comparaison au seuil d'éligibilité."""
    distance_premier_troncon_m: float | None = None
    """Distance à vol d'oiseau entre le point de départ saisi (point d'analyse) et le
    premier point de la géométrie renvoyée par l'itinéraire IGN. Le point de départ n'est
    pas toujours situé exactement sur une route (immeuble, place...) : l'API de routage
    IGN projette alors la requête sur le point routable le plus proche de son propre
    graphe avant de calculer l'itinéraire, un écart que `itineraire.distance_m` ne couvre
    pas. Nul si le point de départ est déjà sur le réseau routier utilisé par l'API."""
    distance_dernier_troncon_m: float | None = None
    """Distance à vol d'oiseau entre point_le_plus_proche (sur la route candidate) et le
    point le plus proche du réseau BT réel — voir geo/candidates.py::distance_au_reseau_bt.
    Toujours <= buffer_m par construction (le candidat est une portion de route incluse
    dans le buffer autour du réseau BT)."""


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
    """Distance totale départ -> réseau BT : distance_premier_troncon_m +
    distance_itineraire_m + distance_dernier_troncon_m. C'est cette distance totale (pas
    seulement le tronçon de voirie) qui est comparée au seuil d'éligibilité — voir
    RankedCandidate.distance_routiere_m."""
    point_raccordement: PointGeo
    eligible: bool
    candidat: CandidateSegment
    itineraire: Itineraire | None = None
    distance_premier_troncon_m: float = 0.0
    """Distance à vol d'oiseau point de départ (point d'analyse) -> point réellement pris
    comme origine par l'itinéraire IGN (nul si le point d'analyse est déjà sur la route).
    Voir RankedCandidate.distance_premier_troncon_m."""
    distance_itineraire_m: float = 0.0
    """Distance piétonne (IGN) départ -> point_raccordement (sur la route candidate),
    sans le premier ni le dernier tronçon — équivaut à itineraire.distance_m."""
    distance_dernier_troncon_m: float = 0.0
    """Distance à vol d'oiseau point_raccordement -> câble BT le plus proche (le tronçon
    non couvert par le réseau routier, <= buffer_m). Voir RankedCandidate."""
    repartition_type_m: dict[str, float] = field(default_factory=dict)
    """Longueur de l'itinéraire (mètres) par nature de voie traversée — voir
    geo/itineraire.py::repartir_longueur_par_type. Vide si l'itinéraire n'a pas de
    géométrie exploitable."""
