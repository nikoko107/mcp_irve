from pytest import approx
from shapely.geometry import LineString

from mcp_irve.geo.itineraire import TYPE_NON_IDENTIFIE, repartir_longueur_par_type
from mcp_irve.models import RouteSegment

TOLERANCE_M = 2.0


def _route(id_, geometry, nature="Route à 1 chaussée"):
    return RouteSegment(id=id_, nature=nature, geometry=geometry, attributes={})


def test_itineraire_coincide_avec_un_unique_troncon():
    route = _route("route-1", LineString([(0, 0), (100, 0)]))
    itineraire = LineString([(0, 0), (100, 0)])

    repartition = repartir_longueur_par_type(itineraire, [route], TOLERANCE_M)

    assert repartition == {"Route à 1 chaussée": approx(100.0, abs=1e-3)}


def test_itineraire_traverse_deux_troncons_bout_a_bout():
    # Deux tronçons adjacents de natures différentes, mis bout à bout : l'itinéraire
    # emprunte l'ensemble, sans résidu notable.
    route_1 = _route("route-1", LineString([(0, 0), (50, 0)]), nature="Route à 1 chaussée")
    route_2 = _route("route-2", LineString([(50, 0), (100, 0)]), nature="Chemin")
    itineraire = LineString([(0, 0), (100, 0)])

    repartition = repartir_longueur_par_type(itineraire, [route_1, route_2], TOLERANCE_M)

    assert set(repartition.keys()) == {"Route à 1 chaussée", "Chemin"}
    # Le chevauchement des tolérances aux jonctions peut compter quelques mètres deux
    # fois (documenté dans le docstring du module) : on tolère une petite marge.
    assert repartition["Route à 1 chaussée"] == approx(50.0, abs=TOLERANCE_M)
    assert repartition["Chemin"] == approx(50.0, abs=TOLERANCE_M)
    assert sum(repartition.values()) == approx(itineraire.length, abs=2 * TOLERANCE_M)


def test_itineraire_avec_portion_ne_recoupant_aucun_troncon():
    # Le tronçon connu ne couvre que la première moitié de l'itinéraire (0-50) ; la
    # seconde moitié (50-100) ne recoupe rien et doit apparaître comme non identifiée.
    route = _route("route-1", LineString([(0, 0), (50, 0)]))
    itineraire = LineString([(0, 0), (100, 0)])

    repartition = repartir_longueur_par_type(itineraire, [route], TOLERANCE_M)

    assert TYPE_NON_IDENTIFIE in repartition
    assert repartition["Route à 1 chaussée"] == approx(50.0, abs=TOLERANCE_M)
    assert repartition[TYPE_NON_IDENTIFIE] == approx(50.0, abs=TOLERANCE_M)


def test_reseau_routier_vide_donne_tout_en_non_identifie():
    itineraire = LineString([(0, 0), (100, 0)])

    repartition = repartir_longueur_par_type(itineraire, [], TOLERANCE_M)

    assert repartition == {TYPE_NON_IDENTIFIE: approx(100.0, abs=1e-3)}


def test_ordre_de_tri_decroissant_par_longueur():
    # Trois tronçons de longueurs distinctes et croissantes (10, 30, 60) : le dict
    # retourné doit lister les natures de la plus longue à la plus courte.
    route_courte = _route("route-courte", LineString([(0, 0), (10, 0)]), nature="Chemin")
    route_moyenne = _route(
        "route-moyenne", LineString([(10, 0), (40, 0)]), nature="Route à 1 chaussée"
    )
    route_longue = _route(
        "route-longue", LineString([(40, 0), (100, 0)]), nature="Route à 2 chaussées"
    )
    itineraire = LineString([(0, 0), (100, 0)])

    repartition = repartir_longueur_par_type(
        itineraire, [route_courte, route_moyenne, route_longue], TOLERANCE_M
    )

    assert list(repartition.keys()) == ["Route à 2 chaussées", "Route à 1 chaussée", "Chemin"]
    longueurs = list(repartition.values())
    assert longueurs == sorted(longueurs, reverse=True)
