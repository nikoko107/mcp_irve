"""Filtrage d'accessibilité (étape 4 du pipeline / outil filtrer_candidats_accessibles).

Décision retenue (lecture littérale du cahier des charges, tranchée avec l'utilisateur) :
on bufferise le réseau BT et on découpe les tronçons ROUTIERS partiellement inclus dans
ce buffer. Un candidat représente donc une portion de route suffisamment proche du
réseau BT pour qu'un raccordement y soit plausible — son ``type`` est la nature du
tronçon routier BD TOPO (route, chemin...), pas une typologie aérien/souterrain.

Toutes les géométries en entrée doivent être exprimées dans le CRS de travail
(Lambert 93 / EPSG:2154) : les distances en mètres (buffer, longueur minimale) n'ont
de sens que dans ce référentiel projeté.
"""

from __future__ import annotations

from shapely.geometry import LineString, MultiLineString
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.validation import make_valid

from ..config import SETTINGS
from ..models import CandidateSegment, ReseauSegment, RouteSegment


def _iter_linestrings(geometry: BaseGeometry) -> list[LineString]:
    """Aplatit le résultat d'une intersection en une liste de LineString.

    Une intersection ligne/polygone peut renvoyer un LineString, un MultiLineString,
    ou une GeometryCollection dégénérée contenant un Point isolé lorsque le buffer
    effleure tangentiellement la ligne sans la traverser — ces Points sont ignorés.
    """
    if geometry.is_empty:
        return []
    if isinstance(geometry, LineString):
        return [geometry]
    if isinstance(geometry, MultiLineString):
        return list(geometry.geoms)
    if geometry.geom_type == "GeometryCollection":
        result: list[LineString] = []
        for part in geometry.geoms:
            result.extend(_iter_linestrings(part))
        return result
    return []


def buffer_reseau_bt(reseau_bt: list[ReseauSegment], buffer_m: float) -> BaseGeometry | None:
    """Union des buffers de `buffer_m` autour de chaque tronçon BT — la zone tampon
    telle qu'utilisée par `filtrer_candidats`. Exposée séparément pour que l'appelant
    (pipeline.py) puisse la conserver et l'afficher (carte, export GeoJSON complet)
    sans dupliquer la logique de calcul.
    """
    if not reseau_bt:
        return None
    bt_geoms = [make_valid(seg.geometry) for seg in reseau_bt]
    return unary_union([g.buffer(buffer_m) for g in bt_geoms])


def filtrer_candidats(
    reseau_bt: list[ReseauSegment],
    reseau_routier: list[RouteSegment],
    buffer_m: float,
) -> list[CandidateSegment]:
    """Buffer autour du réseau BT, intersection avec les routes, découpe des tronçons
    routiers partiellement inclus. Un tronçon routier peut produire plusieurs segments
    candidats disjoints (s'il entre et sort du buffer plusieurs fois).
    """
    if not reseau_bt or not reseau_routier:
        return []

    buffer_zone = buffer_reseau_bt(reseau_bt, buffer_m)

    candidats: list[CandidateSegment] = []
    for route in reseau_routier:
        route_geom = make_valid(route.geometry)
        intersection = route_geom.intersection(buffer_zone)
        for i, part in enumerate(_iter_linestrings(intersection)):
            if part.length < SETTINGS.longueur_min_segment_m:
                continue
            candidats.append(
                CandidateSegment(
                    candidate_id=f"{route.id}-{i}",
                    source_troncon_id=route.id,
                    type=route.nature,
                    geometry=part,
                    source_geometry=route.geometry,
                    length_m=part.length,
                )
            )
    return candidats
