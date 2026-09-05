"""Construction d'un SessionState synthétique partagé par les tests de tests/outputs/."""

from __future__ import annotations

from shapely.geometry import LineString, Polygon

from mcp_irve.geo.projections import l93_to_wgs84
from mcp_irve.models import (
    CandidateSegment,
    Itineraire,
    PointGeo,
    ReseauSegment,
    Resultat,
    RouteSegment,
)
from mcp_irve.state import SessionState, Stage

# Géométries synthétiques en Lambert 93 (EPSG:2154), coordonnées rondes plausibles
# pour la France métropolitaine (évite toute surprise de reprojection aux limites du CRS).
DEPART_X, DEPART_Y = 649950.0, 6860002.0
CANDIDAT_GEOM = LineString([(650000.0, 6860000.0), (650100.0, 6860000.0)])
BT_AERIEN_GEOM = LineString([(650000.0, 6860005.0), (650100.0, 6860005.0)])
BT_SOUTERRAIN_GEOM = LineString([(650000.0, 6859995.0), (650100.0, 6859995.0)])
ITINERAIRE_GEOM = LineString([(DEPART_X, DEPART_Y), (650000.0, 6860000.0)])
BUFFER_GEOM = Polygon(
    [(649990.0, 6859985.0), (650110.0, 6859985.0), (650110.0, 6860015.0), (649990.0, 6860015.0)]
)


def build_state(
    *, with_layers: bool = False, eligible: bool = True, adresse: str | None = None
) -> SessionState:
    """Construit un SessionState avec un résultat complet, sans passer par le pipeline."""
    depart_lat, depart_lon = l93_to_wgs84(DEPART_X, DEPART_Y)
    point_raccordement_lat, point_raccordement_lon = l93_to_wgs84(650000.0, 6860000.0)

    state = SessionState(session_id="test-output")
    state.point_depart = PointGeo(lat=depart_lat, lon=depart_lon, x_l93=DEPART_X, y_l93=DEPART_Y)
    state.adresse_normalisee = adresse or "1 rue de Test, 63000 Clermont-Ferrand"
    state.saisie_source = "BAN"
    state.stage = Stage.RESULTAT

    candidat = CandidateSegment(
        candidate_id="route-1-0",
        source_troncon_id="route-1",
        type="Route à 1 chaussée",
        geometry=CANDIDAT_GEOM,
        source_geometry=CANDIDAT_GEOM,
        length_m=CANDIDAT_GEOM.length,
    )
    distance_routiere_m = 150.0 if eligible else 250.0
    itineraire = Itineraire(distance_m=distance_routiere_m, duree_s=120.0, geometry=ITINERAIRE_GEOM)

    state.resultat = Resultat(
        troncon_id="route-1",
        type="Route à 1 chaussée",
        distance_vol_oiseau_m=50.04,
        distance_routiere_m=distance_routiere_m,
        point_raccordement=PointGeo(
            lat=point_raccordement_lat, lon=point_raccordement_lon, x_l93=650000.0, y_l93=6860000.0
        ),
        dans_perimetre_analyse=eligible,
        candidat=candidat,
        itineraire=itineraire,
    )

    if with_layers:
        state.reseau_bt = [
            ReseauSegment(id="bt-1", type="aerien", geometry=BT_AERIEN_GEOM, attributes={}),
            ReseauSegment(id="bt-2", type="souterrain", geometry=BT_SOUTERRAIN_GEOM, attributes={}),
        ]
        state.reseau_routier = [
            RouteSegment(
                id="route-1",
                nature="Route à 1 chaussée",
                geometry=CANDIDAT_GEOM,
                attributes={},
            ),
        ]
        state.candidats = [candidat]
        state.buffer_m = 10
        state.buffer_zone = BUFFER_GEOM

    return state
