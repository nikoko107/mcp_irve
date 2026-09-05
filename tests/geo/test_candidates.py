from pytest import approx
from shapely.geometry import LineString, Point

from mcp_irve.geo.candidates import (
    classer_candidats,
    distance_au_reseau_bt,
    selectionner_n_plus_proches,
)
from mcp_irve.models import CandidateSegment, ReseauSegment

POINT_DEPART = Point(0, 0)


def _reseau_segment(seg_id, geometry, type_="aerien"):
    return ReseauSegment(id=seg_id, type=type_, geometry=geometry, attributes={})


def _candidat(candidate_id, geometry):
    return CandidateSegment(
        candidate_id=candidate_id,
        source_troncon_id=f"source-{candidate_id}",
        type="Route à 1 chaussée",
        geometry=geometry,
        source_geometry=geometry,
        length_m=geometry.length,
    )


def test_classer_candidats_trie_par_distance_a_vol_doiseau_croissante():
    proche = _candidat("proche", LineString([(0, 5), (0, 15)]))  # distance 5
    moyen = _candidat("moyen", LineString([(10, 0), (20, 0)]))  # distance 10
    loin = _candidat("loin", LineString([(100, 100), (110, 100)]))  # distance ~141.4

    ranked = classer_candidats(POINT_DEPART, [loin, proche, moyen])

    assert [rc.candidate.candidate_id for rc in ranked] == ["proche", "moyen", "loin"]
    assert ranked[0].distance_vol_oiseau_m == approx(5.0)
    assert ranked[1].distance_vol_oiseau_m == approx(10.0)
    assert ranked[2].distance_vol_oiseau_m == approx(141.421356, rel=1e-6)


def test_classer_candidats_calcule_le_point_le_plus_proche():
    candidat = _candidat("c", LineString([(0, 5), (0, 15)]))

    ranked = classer_candidats(POINT_DEPART, [candidat])

    point_proche = ranked[0].point_le_plus_proche
    assert point_proche.x == approx(0.0)
    assert point_proche.y == approx(5.0)


def test_classer_candidats_distance_routiere_non_calculee_par_defaut():
    candidat = _candidat("c", LineString([(0, 5), (0, 15)]))

    ranked = classer_candidats(POINT_DEPART, [candidat])

    assert ranked[0].distance_routiere_m is None


def test_classer_candidats_liste_vide():
    assert classer_candidats(POINT_DEPART, []) == []


def test_selectionner_n_plus_proches_tronque_a_n():
    candidats = [
        _candidat("a", LineString([(0, 1), (0, 2)])),
        _candidat("b", LineString([(0, 2), (0, 3)])),
        _candidat("c", LineString([(0, 3), (0, 4)])),
        _candidat("d", LineString([(0, 4), (0, 5)])),
    ]
    ranked = classer_candidats(POINT_DEPART, candidats)

    selection = selectionner_n_plus_proches(ranked, 2)

    assert len(selection) == 2
    assert [rc.candidate.candidate_id for rc in selection] == ["a", "b"]


def test_selectionner_n_plus_proches_n_superieur_a_la_taille_de_la_liste():
    candidats = [_candidat("a", LineString([(0, 1), (0, 2)]))]
    ranked = classer_candidats(POINT_DEPART, candidats)

    selection = selectionner_n_plus_proches(ranked, 5)

    assert len(selection) == 1


def test_distance_au_reseau_bt_un_seul_troncon():
    point = Point(0, 0)
    segment = _reseau_segment("bt-1", LineString([(5, -10), (5, 10)]))

    assert distance_au_reseau_bt(point, [segment]) == approx(5.0)


def test_distance_au_reseau_bt_retient_le_minimum_parmi_plusieurs_troncons():
    point = Point(0, 0)
    proche = _reseau_segment("bt-proche", LineString([(3, -10), (3, 10)]))
    loin = _reseau_segment("bt-loin", LineString([(50, -10), (50, 10)]), type_="souterrain")

    assert distance_au_reseau_bt(point, [loin, proche]) == approx(3.0)
