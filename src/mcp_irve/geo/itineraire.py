"""Répartition de la longueur d'un itinéraire routier par type de voie (étape finale de
l'outil selectionner_meilleur_candidat, appelée juste après le calcul d'itinéraire).

La ressource de routage IGN (``bdtopo-osrm``) construit son graphe à partir des mêmes
tronçons BD TOPO® que ceux récupérés par ``recuperer_reseau_routier`` : la géométrie de
l'itinéraire est donc, hormis un rognage aux deux extrémités, une concaténation des
géométries des tronçons traversés. On attribue chaque portion de l'itinéraire au
tronçon routier avec lequel elle coïncide, en bufferisant chaque tronçon d'une faible
tolérance pour absorber les écarts de tracé mineurs entre le graphe de routage et le
flux WFS (deux jeux de données distincts côté IGN).

Approximatif par construction : aux jonctions entre deux tronçons adjacents, leurs
tolérances respectives se chevauchent sur une distance de l'ordre de la tolérance, ce
qui peut compter deux fois quelques mètres — négligeable face aux longueurs typiques
(dizaines à centaines de mètres). Toute portion de l'itinéraire ne recoupant aucun
tronçon récupéré (hors du rayon de recherche, tronçon absent du flux WFS) est renvoyée
sous la clé ``TYPE_NON_IDENTIFIE``.
"""

from __future__ import annotations

from shapely.geometry.base import BaseGeometry
from shapely.validation import make_valid

from ..models import RouteSegment

TYPE_NON_IDENTIFIE = "Autre / tronçon non identifié"


def repartir_longueur_par_type(
    itineraire_geometry: BaseGeometry,
    reseau_routier: list[RouteSegment],
    tolerance_m: float,
) -> dict[str, float]:
    """Longueur de l'itinéraire (mètres) par nature BD TOPO du tronçon routier traversé.

    L'ordre des clés suit l'ordre décroissant de longueur, du type le plus emprunté au
    moins emprunté — pratique pour un affichage direct (rapport, carte) sans retri.
    """
    repartition: dict[str, float] = {}
    longueur_attribuee = 0.0
    for route in reseau_routier:
        zone = make_valid(route.geometry).buffer(tolerance_m)
        longueur = itineraire_geometry.intersection(zone).length
        if longueur > 0:
            repartition[route.nature] = repartition.get(route.nature, 0.0) + longueur
            longueur_attribuee += longueur

    residu = itineraire_geometry.length - longueur_attribuee
    if residu > tolerance_m:  # au-delà du bruit de chevauchement attendu aux jonctions
        repartition[TYPE_NON_IDENTIFIE] = residu

    return dict(sorted(repartition.items(), key=lambda item: item[1], reverse=True))
