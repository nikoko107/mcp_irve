from pytest import approx
from shapely.geometry import LineString

from mcp_irve.config import SETTINGS
from mcp_irve.geo.accessibility import filtrer_candidats
from mcp_irve.models import ReseauSegment, RouteSegment

BUFFER_M = 10.0


def _bt(id_, geometry, type_="aerien"):
    return ReseauSegment(id=id_, type=type_, geometry=geometry, attributes={})


def _route(id_, geometry, nature="Route à 1 chaussée"):
    return RouteSegment(id=id_, nature=nature, geometry=geometry, attributes={})


def test_route_entierement_dans_le_buffer_donne_un_candidat_couvrant_tout_le_troncon():
    # BT parallèle à 5 m de la route, sur toute sa longueur : la route entière (0-100)
    # est bien à l'intérieur du buffer de 10 m.
    reseau_bt = [_bt("bt-1", LineString([(0, 5), (100, 5)]))]
    reseau_routier = [_route("route-1", LineString([(0, 0), (100, 0)]))]

    candidats = filtrer_candidats(reseau_bt, reseau_routier, BUFFER_M)

    assert len(candidats) == 1
    candidat = candidats[0]
    assert candidat.source_troncon_id == "route-1"
    assert candidat.type == "Route à 1 chaussée"
    assert candidat.length_m == approx(100.0, abs=1e-3)
    assert candidat.geometry.length == approx(100.0, abs=1e-3)
    assert candidat.source_geometry.length == approx(100.0)


def test_route_entierement_hors_buffer_donne_aucun_candidat():
    # BT à 1000 m de la route : hors de portée du buffer de 10 m.
    reseau_bt = [_bt("bt-1", LineString([(0, 1000), (100, 1000)]))]
    reseau_routier = [_route("route-1", LineString([(0, 0), (100, 0)]))]

    candidats = filtrer_candidats(reseau_bt, reseau_routier, BUFFER_M)

    assert candidats == []


def test_route_chevauche_partiellement_le_buffer_donne_un_candidat_plus_court():
    # BT court (x de 0 à 30) à 5 m de la route : une extrémité de la route (x=0) est
    # dans le buffer, l'autre (x=100) en est loin.
    reseau_bt = [_bt("bt-1", LineString([(0, 5), (30, 5)]))]
    reseau_routier = [_route("route-1", LineString([(0, 0), (100, 0)]))]

    candidats = filtrer_candidats(reseau_bt, reseau_routier, BUFFER_M)

    assert len(candidats) == 1
    candidat = candidats[0]
    # Portion couverte ~ x in [0, 30 + sqrt(10^2 - 5^2)] = [0, ~38.66], donc strictement
    # plus courte que le tronçon source (100 m) mais plus longue que la partie
    # "interne" garantie (30 m).
    assert 30.0 < candidat.length_m < 40.0
    assert candidat.length_m < candidat.source_geometry.length
    min_x, _, max_x, _ = candidat.geometry.bounds
    assert min_x == approx(0.0, abs=1e-6)
    assert 35.0 < max_x < 40.0


def test_route_traverse_le_buffer_deux_fois_donne_deux_candidats_disjoints():
    # Deux tronçons BT séparés le long de la route (perpendiculaires, en x=20 et
    # x=80) : la route entre-sort du buffer deux fois -> deux segments candidats
    # disjoints.
    reseau_bt = [
        _bt("bt-1", LineString([(20, -15), (20, 15)])),
        _bt("bt-2", LineString([(80, -15), (80, 15)])),
    ]
    reseau_routier = [_route("route-1", LineString([(0, 0), (100, 0)]))]

    candidats = filtrer_candidats(reseau_bt, reseau_routier, BUFFER_M)

    assert len(candidats) == 2
    longueurs = sorted(c.length_m for c in candidats)
    assert longueurs[0] == approx(20.0, abs=1e-6)
    assert longueurs[1] == approx(20.0, abs=1e-6)

    bounds = sorted(c.geometry.bounds[0] for c in candidats)  # min_x de chaque candidat
    assert bounds[0] == approx(10.0, abs=1e-6)
    assert bounds[1] == approx(70.0, abs=1e-6)

    # Les deux candidats proviennent du même tronçon routier source.
    assert all(c.source_troncon_id == "route-1" for c in candidats)
    # Segments disjoints : le premier se termine avant que le second ne commence.
    max_x_premier = min(candidats, key=lambda c: c.geometry.bounds[0]).geometry.bounds[2]
    min_x_second = max(candidats, key=lambda c: c.geometry.bounds[0]).geometry.bounds[0]
    assert max_x_premier < min_x_second


def test_segment_plus_court_que_longueur_min_est_exclu():
    # Buffer très fin (0.3 m) : la route ne fait qu'effleurer le buffer BT sur une
    # largeur de 2*0.3 = 0.6 m, en-deçà de SETTINGS.longueur_min_segment_m (1.0 m).
    assert SETTINGS.longueur_min_segment_m == 1.0
    petit_buffer_m = 0.3
    reseau_bt = [_bt("bt-1", LineString([(50, -5), (50, 5)]))]
    reseau_routier = [_route("route-1", LineString([(0, 0), (100, 0)]))]

    candidats = filtrer_candidats(reseau_bt, reseau_routier, petit_buffer_m)

    assert candidats == []


def test_reseau_bt_ou_routier_vide_donne_aucun_candidat():
    route = _route("route-1", LineString([(0, 0), (100, 0)]))
    bt = _bt("bt-1", LineString([(0, 5), (100, 5)]))

    assert filtrer_candidats([], [route], BUFFER_M) == []
    assert filtrer_candidats([bt], [], BUFFER_M) == []
