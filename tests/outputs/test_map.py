import json
import re

from mcp_irve.outputs import map as map_output

from ._helpers import build_state

_GEOJSON_RE = re.compile(r"const geojson = (.*?);\n\nconst styleByLayer", re.DOTALL)


def _extract_embedded_geojson(html: str) -> dict:
    match = _GEOJSON_RE.search(html)
    assert match is not None, "bloc 'const geojson = ...;' introuvable dans le HTML généré"
    return json.loads(match.group(1))


def test_carte_html_contient_la_projection_et_ladresse(patch_output_dir):
    state = build_state(with_layers=True)

    chemin = map_output.generer_carte_html(state)
    html = chemin.read_text(encoding="utf-8")

    assert "EPSG:2154" in html
    assert "proj4.defs" in html
    assert state.adresse_normalisee in html


def test_carte_html_contient_le_fond_orthophoto(patch_output_dir):
    state = build_state(with_layers=True)

    chemin = map_output.generer_carte_html(state)
    html = chemin.read_text(encoding="utf-8")

    assert "ORTHOIMAGERY.ORTHOPHOTOS" in html
    assert "orthophotoLayer" in html
    # la vue reste en Lambert 93 malgré le fond en Web Mercator (reprojection à la volée)
    assert "EPSG:3857" in html
    assert "layers: [orthophotoLayer, liveReseauLayer, vectorLayer, livePosteLayer]" in html


def test_carte_html_contient_le_reseau_en_direct(patch_output_dir):
    from mcp_irve.config import SETTINGS

    state = build_state(with_layers=True)

    chemin = map_output.generer_carte_html(state)
    html = chemin.read_text(encoding="utf-8")

    assert SETTINGS.enedis_base_url in html
    assert f'"{SETTINGS.enedis_dataset_aerien}"' in html
    assert f'"{SETTINGS.enedis_dataset_souterrain}"' in html
    assert f'"{SETTINGS.enedis_dataset_poste}"' in html
    assert "chargerReseauEnDirect" in html
    assert "within_distance(geometry" in html
    assert "map.on('moveend'" in html


def test_carte_html_contient_la_zone_tampon(patch_output_dir):
    state = build_state(with_layers=True)

    chemin = map_output.generer_carte_html(state)
    html = chemin.read_text(encoding="utf-8")

    geojson = _extract_embedded_geojson(html)
    layers = {f["properties"]["layer"] for f in geojson["features"]}
    assert "buffer" in layers
    assert "Zone tampon" in html


def test_carte_html_embarque_toutes_les_features(patch_output_dir):
    state = build_state(with_layers=True)

    chemin = map_output.generer_carte_html(state)
    html = chemin.read_text(encoding="utf-8")

    geojson = _extract_embedded_geojson(html)
    assert geojson["type"] == "FeatureCollection"

    from mcp_irve.outputs._shared import construire_features

    # Le réseau BT n'est pas embarqué (il est chargé en direct depuis l'API Enedis, en
    # JS, au chargement de la page) — voir test_carte_html_contient_le_fond_orthophoto.
    attendu = construire_features(state, "complet", inclure_reseau_bt=False)
    assert len(geojson["features"]) == len(attendu)
    couches_embarquees = {f["properties"]["layer"] for f in geojson["features"]}
    assert couches_embarquees.isdisjoint({"bt_aerien", "bt_souterrain"})


def test_carte_html_echappe_les_scripts_dans_ladresse(patch_output_dir):
    payload = "</script><script>alert(1)</script>"
    state = build_state(with_layers=False, adresse=f"1 rue Test {payload}")

    chemin = map_output.generer_carte_html(state)
    html = chemin.read_text(encoding="utf-8")

    # La séquence brute ne doit apparaître nulle part : ni dans le texte affiché
    # (échappé par le filtre Jinja2 |e), ni dans le JSON embarqué (où "</" est
    # transformé en "<\/" pour ne pas pouvoir clore la balise <script>).
    assert "</script><script>" not in html

    # Version échappée pour l'affichage (titre + légende).
    assert "&lt;/script&gt;&lt;script&gt;alert(1)&lt;/script&gt;" in html

    # Version échappée dans le JSON embarqué : "</" -> "<\/".
    assert "<\\/script>" in html

    # Le GeoJSON embarqué reste malgré tout un JSON valide une fois décodé.
    geojson = _extract_embedded_geojson(html)
    depart_feature = next(f for f in geojson["features"] if f["properties"]["layer"] == "depart")
    assert depart_feature["properties"]["adresse"] == state.adresse_normalisee
