"""Classement des candidats par distance à vol d'oiseau (étape 5 du pipeline,
première moitié de l'outil selectionner_meilleur_candidat).

Le point de départ et les géométries candidates doivent être dans le même CRS
(Lambert 93 / EPSG:2154) pour que les distances calculées soient en mètres.
"""

from __future__ import annotations

from shapely.geometry import Point
from shapely.ops import nearest_points

from ..models import CandidateSegment, RankedCandidate


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
