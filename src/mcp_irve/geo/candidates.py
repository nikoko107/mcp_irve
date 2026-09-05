"""Classement des candidats par distance à vol d'oiseau (étape 5 du pipeline,
première moitié de l'outil selectionner_meilleur_candidat).

Le point de départ et les géométries candidates doivent être dans le même CRS
(Lambert 93 / EPSG:2154) pour que les distances calculées soient en mètres.
"""

from __future__ import annotations

from shapely.geometry import Point
from shapely.ops import nearest_points

from ..models import CandidateSegment, RankedCandidate, ReseauSegment


def classer_candidats(
    point_depart: Point, candidats: list[CandidateSegment]
) -> list[RankedCandidate]:
    """Classe les candidats par distance à vol d'oiseau croissante entre le point de
    départ et le point projeté le plus proche sur chaque segment candidat.
    """
    ranked: list[RankedCandidate] = []
    for candidat in candidats:
        _, point_proche = nearest_points(point_depart, candidat.geometry)
        ranked.append(
            RankedCandidate(
                candidate=candidat,
                point_le_plus_proche=point_proche,
                distance_vol_oiseau_m=point_depart.distance(candidat.geometry),
            )
        )
    ranked.sort(key=lambda rc: rc.distance_vol_oiseau_m)
    return ranked


def selectionner_n_plus_proches(
    ranked: list[RankedCandidate], n: int
) -> list[RankedCandidate]:
    return ranked[:n]


def distance_au_reseau_bt(point: Point, reseau_bt: list[ReseauSegment]) -> float:
    """Distance à vol d'oiseau entre `point` (sur la route candidate) et le câble BT le
    plus proche — le dernier tronçon non couvert par le réseau routier, entre la voirie
    et le réseau électrique réel. Toujours <= buffer_m par construction : `point` est le
    point le plus proche d'une route candidate, elle-même une portion incluse dans le
    buffer `buffer_m` autour du réseau BT (voir geo/accessibility.py::filtrer_candidats).
    """
    return min(point.distance(seg.geometry) for seg in reseau_bt)
