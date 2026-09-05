"""Génération de la carte interactive HTML (outil generer_carte).

Le GeoJSON (toutes couches, WGS84) est embarqué inline dans le HTML plutôt que chargé
via un fichier séparé : un `fetch()` local est bloqué par CORS quand l'utilisateur ouvre
le fichier directement dans un navigateur (`file://`), qui est l'usage attendu ici.

OpenLayers ne connaît pas EPSG:2154 (Lambert 93) nativement — la projection est
enregistrée côté client via proj4js dans le template (voir templates/map.html.j2).
"""

from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from ..config import SETTINGS
from ..state import SessionState
from ._shared import construire_features, new_output_path

_env = Environment(loader=FileSystemLoader(str(SETTINGS.templates_dir)), autoescape=False)


def generer_carte_html(state: SessionState) -> Path:
    # Le réseau BT n'est pas figé dans le GeoJSON embarqué : la carte l'affiche en
    # direct depuis l'API Enedis (voir templates/map.html.j2), pour rester à jour
    # quand on déplace/zoome la carte au lieu de se limiter au rayon de l'analyse.
    features = construire_features(state, "complet", inclure_reseau_bt=False)
    geojson = {"type": "FeatureCollection", "features": features}

    # échappe "</" pour qu'une valeur contenant littéralement "</script>" ne puisse
    # pas clore prématurément la balise <script> dans laquelle le JSON est embarqué
    geojson_str = json.dumps(geojson, ensure_ascii=False).replace("</", "<\\/")

    resultat = state.resultat
    distance_routiere_m = round(resultat.distance_routiere_m, 1) if resultat is not None else None
    repartition_type_m = (
        {k: round(v, 1) for k, v in resultat.repartition_type_m.items()}
        if resultat is not None
        else {}
    )
    template = _env.get_template("map.html.j2")
    html = template.render(
        adresse=state.adresse_normalisee or "",
        geojson_str=geojson_str,
        dans_perimetre_analyse=resultat.dans_perimetre_analyse if resultat is not None else None,
        distance_routiere_m=distance_routiere_m,
        repartition_type_m=repartition_type_m,
        perimetre_m=SETTINGS.perimetre_analyse_m,
        enedis_base_url=SETTINGS.enedis_base_url,
        enedis_dataset_aerien=SETTINGS.enedis_dataset_aerien,
        enedis_dataset_souterrain=SETTINGS.enedis_dataset_souterrain,
        enedis_dataset_poste=SETTINGS.enedis_dataset_poste,
    )

    chemin = new_output_path("carte", "html")
    chemin.write_text(html, encoding="utf-8")
    return chemin
