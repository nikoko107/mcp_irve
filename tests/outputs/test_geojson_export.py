import json

from mcp_irve.outputs import geojson_export

from ._helpers import build_state

LAYERS_RESULTAT_MINIMUM = {"depart", "resultat", "point_raccordement", "itineraire"}
LAYERS_COMPLET_SUPPLEMENTAIRES = {"buffer", "bt_aerien", "bt_souterrain", "routes", "candidats"}


def _assert_wgs84_plausible(lon: float, lat: float) -> None:
    # Une valeur Lambert 93 typique (x~650000, y~6860000) serait immédiatement hors de
    # ces bornes ; ce test garantit qu'on n'a pas oublié une reprojection quelque part.
    assert -180.0 <= lon <= 180.0
    assert -90.0 <= lat <= 90.0
    assert abs(lon) < 20.0  # plausible pour la France métropolitaine
    assert 35.0 < lat < 55.0


def _iter_all_coords(geometry: dict):
    coords = geometry["coordinates"]
    gtype = geometry["type"]
    if gtype == "Point":
        yield coords
    elif gtype in ("LineString", "MultiPoint"):
        yield from coords
    elif gtype in ("MultiLineString", "Polygon"):
        for part in coords:
            yield from part
    else:
        raise AssertionError(f"Type de géométrie non couvert par ce test : {gtype}")


def test_export_niveau_resultat_est_un_geojson_valide_en_wgs84(patch_output_dir):
    state = build_state(with_layers=True)

    chemin = geojson_export.exporter_geojson(state, "resultat")

    data = json.loads(chemin.read_text())
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) > 0
    for feature in data["features"]:
        assert feature["type"] == "Feature"
        for lon, lat in _iter_all_coords(feature["geometry"]):
            _assert_wgs84_plausible(lon, lat)


def test_export_niveau_resultat_ne_contient_pas_les_couches_reseau(patch_output_dir):
    state = build_state(with_layers=True)

    chemin = geojson_export.exporter_geojson(state, "resultat")
    data = json.loads(chemin.read_text())

    layers = {f["properties"]["layer"] for f in data["features"]}
    assert layers == LAYERS_RESULTAT_MINIMUM


def test_export_niveau_complet_contient_toutes_les_couches(patch_output_dir):
    state = build_state(with_layers=True)

    chemin = geojson_export.exporter_geojson(state, "complet")
    data = json.loads(chemin.read_text())

    layers = {f["properties"]["layer"] for f in data["features"]}
    assert layers == LAYERS_RESULTAT_MINIMUM | LAYERS_COMPLET_SUPPLEMENTAIRES


def test_export_niveau_complet_sans_itineraire(patch_output_dir):
    state = build_state(with_layers=True)
    state.resultat.itineraire = None

    chemin = geojson_export.exporter_geojson(state, "complet")
    data = json.loads(chemin.read_text())

    layers = {f["properties"]["layer"] for f in data["features"]}
    assert "itineraire" not in layers


def test_export_niveau_complet_contient_la_zone_tampon(patch_output_dir):
    state = build_state(with_layers=True)

    chemin = geojson_export.exporter_geojson(state, "complet")
    data = json.loads(chemin.read_text())

    buffer_feature = next(f for f in data["features"] if f["properties"]["layer"] == "buffer")
    assert buffer_feature["geometry"]["type"] in ("Polygon", "MultiPolygon")
    assert buffer_feature["properties"]["buffer_m"] == state.buffer_m
    for lon, lat in _iter_all_coords(buffer_feature["geometry"]):
        _assert_wgs84_plausible(lon, lat)


def test_export_sans_buffer_zone_omet_la_couche_buffer(patch_output_dir):
    state = build_state(with_layers=True)
    state.buffer_zone = None

    chemin = geojson_export.exporter_geojson(state, "complet")
    data = json.loads(chemin.read_text())

    layers = {f["properties"]["layer"] for f in data["features"]}
    assert "buffer" not in layers


def test_export_niveau_resultat_omet_acces_voirie_quand_distance_nulle(patch_output_dir):
    state = build_state(with_layers=True)
    assert state.resultat.distance_premier_troncon_m == 0.0

    chemin = geojson_export.exporter_geojson(state, "resultat")
    data = json.loads(chemin.read_text())

    layers = {f["properties"]["layer"] for f in data["features"]}
    assert "acces_voirie" not in layers


def test_export_niveau_resultat_contient_acces_voirie_quand_distance_non_nulle(patch_output_dir):
    state = build_state(with_layers=True)
    state.resultat.distance_premier_troncon_m = 5.0

    chemin = geojson_export.exporter_geojson(state, "resultat")
    data = json.loads(chemin.read_text())

    acces_voirie_feature = next(
        f for f in data["features"] if f["properties"]["layer"] == "acces_voirie"
    )
    assert acces_voirie_feature["geometry"]["type"] == "LineString"
    assert acces_voirie_feature["properties"]["distance_m"] == 5.0
    for lon, lat in _iter_all_coords(acces_voirie_feature["geometry"]):
        _assert_wgs84_plausible(lon, lat)


def test_export_proprietes_resultat_portent_les_bonnes_valeurs(patch_output_dir):
    state = build_state(with_layers=False, eligible=False)

    chemin = geojson_export.exporter_geojson(state, "resultat")
    data = json.loads(chemin.read_text())

    resultat_feature = next(f for f in data["features"] if f["properties"]["layer"] == "resultat")
    assert resultat_feature["properties"]["eligible"] is False
    assert resultat_feature["properties"]["troncon_id"] == "route-1"
    assert resultat_feature["properties"]["distance_routiere_m"] == 250.0
