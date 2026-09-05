"""Tests d'orchestration bout-en-bout des 9 outils du pipeline.

On ne mocke pas au niveau HTTP (respx) ici : les géométries réelles BAN/Enedis/BD TOPO
ne s'alignent pas forcément dans un buffer de 10 m une fois reprojetées, ce qui serait
fragile à construire à la main. À la place, on monkeypatch directement les fonctions
clientes utilisées par ``pipeline.py`` pour contrôler des géométries synthétiques
simples qui s'intersectent garanti par construction (réseau BT et réseau routier
tous deux autour de coordonnées Lambert 93 rondes, x=650000, y=6860000).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from shapely.geometry import LineString

from mcp_irve import pipeline
from mcp_irve.errors import EtatManquantError, MCPIrveError
from mcp_irve.geo import itineraire as itineraire_geo
from mcp_irve.geo.projections import l93_to_wgs84
from mcp_irve.models import Itineraire, PointGeo, ReseauSegment, RouteSegment
from mcp_irve.state import Stage, get_state

# --- Géométrie synthétique commune ---
#
# Réseau BT aérien à 5 m au nord de la route, sur toute sa longueur (buffer 10 m ->
# la route entière est candidate). Le point de départ est à 50 m à l'ouest du début
# de la route.
BT_LINE = LineString([(650000.0, 6860005.0), (650100.0, 6860005.0)])
ROUTE_LINE = LineString([(650000.0, 6860000.0), (650100.0, 6860000.0)])
DEPART_X, DEPART_Y = 649950.0, 6860002.0
DEPART_LAT, DEPART_LON = l93_to_wgs84(DEPART_X, DEPART_Y)

ADRESSE = "1 rue de Test, 63000 Clermont-Ferrand"


def _make_fake_geocoder(adresse: str = ADRESSE):
    async def fake_geocoder(http, saisie):
        point = PointGeo(lat=DEPART_LAT, lon=DEPART_LON, x_l93=DEPART_X, y_l93=DEPART_Y)
        return point, adresse

    return fake_geocoder


async def fake_recuperer_troncons_proches(http, lat, lon, rayon_m):
    aeriens = [ReseauSegment(id="bt-1", type="aerien", geometry=BT_LINE, attributes={})]
    return aeriens, []


async def fake_recuperer_routes_proches(http, lat, lon, rayon_m):
    return [
        RouteSegment(id="route-1", nature="Route à 1 chaussée", geometry=ROUTE_LINE, attributes={})
    ]


async def fake_recuperer_troncons_lointains(http, lat, lon, rayon_m):
    loin = LineString([(650000.0, 6861000.0), (650100.0, 6861000.0)])
    return [ReseauSegment(id="bt-loin", type="aerien", geometry=loin, attributes={})], []


def _make_fake_itineraire(distance_m: float):
    async def fake_calculer_itineraire(http, start_lat, start_lon, end_lat, end_lon):
        geometry = LineString([(DEPART_X, DEPART_Y), (650000.0, 6860000.0)])
        return Itineraire(distance_m=distance_m, duree_s=distance_m * 0.8, geometry=geometry)

    return fake_calculer_itineraire


def _patch_clients(monkeypatch, distance_m: float, adresse: str | None = None):
    monkeypatch.setattr(
        pipeline.ban_client, "geocoder_adresse", _make_fake_geocoder(adresse or ADRESSE)
    )
    monkeypatch.setattr(
        pipeline.enedis_client, "recuperer_troncons", fake_recuperer_troncons_proches
    )
    monkeypatch.setattr(
        pipeline.geoplateforme_client, "recuperer_routes", fake_recuperer_routes_proches
    )
    monkeypatch.setattr(
        pipeline.geoplateforme_client, "calculer_itineraire", _make_fake_itineraire(distance_m)
    )


# --- Séquence complète, scénario éligible ---


@pytest.mark.asyncio
async def test_sequence_complete_eligible(monkeypatch, patch_output_dir):
    _patch_clients(monkeypatch, distance_m=150.0)
    state = get_state("e2e-eligible")

    geocodage = await pipeline.geocoder_entree(state, None, ADRESSE)
    assert state.stage is Stage.GEOCODED
    assert geocodage["adresse_normalisee"]

    reseau_bt_res = await pipeline.recuperer_reseau_bt(
        state, None, geocodage["lat"], geocodage["lon"]
    )
    assert reseau_bt_res == {"nb_troncons_aeriens": 1, "nb_troncons_souterrains": 0}
    assert state.stage is Stage.RESEAU_BT

    reseau_routier_res = await pipeline.recuperer_reseau_routier(
        state, None, geocodage["lat"], geocodage["lon"]
    )
    assert reseau_routier_res == {"nb_troncons_routes": 1}
    assert state.stage is Stage.RESEAU_ROUTIER

    candidats_res = pipeline.filtrer_candidats_accessibles(state)
    assert candidats_res["nb_candidats_retenus"] == 1
    assert state.stage is Stage.CANDIDATS_FILTRES

    resultat = await pipeline.selectionner_meilleur_candidat(state, None)
    assert state.stage is Stage.RESULTAT
    assert resultat["dans_perimetre_analyse"] is True
    assert resultat["distance_routiere_m"] == pytest.approx(155.0)
    assert resultat["distance_itineraire_m"] == pytest.approx(150.0)
    assert resultat["distance_dernier_troncon_m"] == pytest.approx(5.0)
    assert state.resultat is not None
    assert state.resultat.dans_perimetre_analyse is True
    # L'itinéraire mocké (fake_calculer_itineraire) ne longe route-1 (seul tronçon du
    # réseau routier) que sur sa toute dernière portion (il rejoint le début de la
    # route en ligne droite depuis le point de départ) : l'essentiel de sa longueur
    # est donc non identifié, le reste attribué à la nature de route-1. Le dernier
    # tronçon route -> câble BT (5.0 m, à vol d'oiseau) forme un seau supplémentaire.
    # On vérifie la présence des trois clés et que la somme couvre bien la longueur
    # totale de l'itinéraire, plus ce dernier tronçon.
    repartition = state.resultat.repartition_type_m
    assert set(repartition.keys()) == {
        "Route à 1 chaussée",
        itineraire_geo.TYPE_NON_IDENTIFIE,
        itineraire_geo.RACCORDEMENT_RESEAU_BT,
    }
    assert repartition[itineraire_geo.RACCORDEMENT_RESEAU_BT] == pytest.approx(5.0)
    assert sum(repartition.values()) == pytest.approx(
        state.resultat.itineraire.geometry.length + 5.0, abs=1e-2
    )
    assert resultat["repartition_type_m"].keys() == repartition.keys()

    carte = pipeline.generer_carte(state)
    geojson = pipeline.exporter_geojson(state, "complet")
    pdf = pipeline.generer_rapport_pdf(state)

    assert Path(carte["chemin_fichier"]).is_file()
    assert Path(geojson["chemin_fichier"]).is_file()
    assert Path(pdf["chemin_fichier"]).is_file()
    for chemin in (carte["chemin_fichier"], geojson["chemin_fichier"], pdf["chemin_fichier"]):
        assert Path(chemin).parent == patch_output_dir


@pytest.mark.asyncio
async def test_distance_premier_troncon_non_nulle(monkeypatch, patch_output_dir):
    # Variante de l'itinéraire mocké dont le premier point de la géométrie diffère du
    # point de départ envoyé dans la requête (l'API IGN projette sur son propre graphe
    # avant de router) : écart connu de 5.0 m par Pythagore (3-4-5).
    async def fake_calculer_itineraire_decale(http, start_lat, start_lon, end_lat, end_lon):
        geometry = LineString([(DEPART_X + 3.0, DEPART_Y + 4.0), (650000.0, 6860000.0)])
        return Itineraire(distance_m=150.0, duree_s=150.0 * 0.8, geometry=geometry)

    monkeypatch.setattr(pipeline.ban_client, "geocoder_adresse", _make_fake_geocoder(ADRESSE))
    monkeypatch.setattr(
        pipeline.enedis_client, "recuperer_troncons", fake_recuperer_troncons_proches
    )
    monkeypatch.setattr(
        pipeline.geoplateforme_client, "recuperer_routes", fake_recuperer_routes_proches
    )
    monkeypatch.setattr(
        pipeline.geoplateforme_client,
        "calculer_itineraire",
        fake_calculer_itineraire_decale,
    )

    state = get_state("e2e-premier-troncon")

    geocodage = await pipeline.geocoder_entree(state, None, ADRESSE)
    await pipeline.recuperer_reseau_bt(state, None, geocodage["lat"], geocodage["lon"])
    await pipeline.recuperer_reseau_routier(state, None, geocodage["lat"], geocodage["lon"])
    pipeline.filtrer_candidats_accessibles(state)
    resultat = await pipeline.selectionner_meilleur_candidat(state, None)

    assert resultat["distance_premier_troncon_m"] == pytest.approx(5.0)
    # Total = premier tronçon (5.0) + itinéraire piéton (150.0) + dernier tronçon (5.0).
    assert resultat["distance_routiere_m"] == pytest.approx(160.0)
    assert resultat["distance_itineraire_m"] == pytest.approx(150.0)
    assert resultat["distance_dernier_troncon_m"] == pytest.approx(5.0)

    assert state.resultat.repartition_type_m[itineraire_geo.ACCES_VOIRIE] == pytest.approx(5.0)


# --- Séquence complète, scénario non-éligible ---


@pytest.mark.asyncio
async def test_sequence_complete_non_eligible(monkeypatch, patch_output_dir):
    _patch_clients(monkeypatch, distance_m=250.0)
    state = get_state("e2e-non-eligible")

    geocodage = await pipeline.geocoder_entree(state, None, ADRESSE)
    await pipeline.recuperer_reseau_bt(state, None, geocodage["lat"], geocodage["lon"])
    await pipeline.recuperer_reseau_routier(state, None, geocodage["lat"], geocodage["lon"])
    pipeline.filtrer_candidats_accessibles(state)
    resultat = await pipeline.selectionner_meilleur_candidat(state, None)

    assert resultat["dans_perimetre_analyse"] is False
    assert resultat["distance_routiere_m"] == pytest.approx(255.0)
    assert state.resultat.dans_perimetre_analyse is False

    pdf = pipeline.generer_rapport_pdf(state)
    assert Path(pdf["chemin_fichier"]).is_file()


# --- analyser_raccordement (orchestrateur) ---


@pytest.mark.asyncio
async def test_analyser_raccordement_renvoie_le_contrat_attendu(monkeypatch, patch_output_dir):
    _patch_clients(monkeypatch, distance_m=150.0)
    state = get_state("e2e-orchestrateur-defauts")

    resultat = await pipeline.analyser_raccordement(state, None, ADRESSE)

    assert set(resultat.keys()) == {
        "adresse_normalisee",
        "distance_routiere_m",
        "dans_perimetre_analyse",
        "chemins_fichiers",
    }
    assert resultat["dans_perimetre_analyse"] is True
    # Flags par défaut : carte + pdf générés, geojson non généré.
    assert set(resultat["chemins_fichiers"].keys()) == {"carte", "pdf"}
    for chemin in resultat["chemins_fichiers"].values():
        assert Path(chemin).is_file()


@pytest.mark.asyncio
async def test_analyser_raccordement_respecte_les_flags(monkeypatch, patch_output_dir):
    _patch_clients(monkeypatch, distance_m=150.0)
    state = get_state("e2e-orchestrateur-flags")

    resultat = await pipeline.analyser_raccordement(
        state,
        None,
        ADRESSE,
        generer_carte_flag=False,
        generer_pdf_flag=False,
        generer_geojson_flag=True,
    )

    assert set(resultat["chemins_fichiers"].keys()) == {"geojson"}
    assert Path(resultat["chemins_fichiers"]["geojson"]).is_file()


@pytest.mark.asyncio
async def test_analyser_raccordement_sans_aucune_sortie(monkeypatch, patch_output_dir):
    _patch_clients(monkeypatch, distance_m=150.0)
    state = get_state("e2e-orchestrateur-aucune-sortie")

    resultat = await pipeline.analyser_raccordement(
        state,
        None,
        ADRESSE,
        generer_carte_flag=False,
        generer_pdf_flag=False,
        generer_geojson_flag=False,
    )

    assert resultat["chemins_fichiers"] == {}


# --- Garde-fous d'ordre ---


@pytest.mark.asyncio
async def test_appel_sans_etape_prealable_leve_etat_manquant():
    state = get_state("e2e-ordre-frais")
    assert state.stage is Stage.EMPTY

    with pytest.raises(EtatManquantError):
        pipeline.filtrer_candidats_accessibles(state)


@pytest.mark.asyncio
async def test_selectionner_candidat_sans_filtrage_leve_etat_manquant():
    state = get_state("e2e-ordre-selection")
    assert state.stage is Stage.EMPTY

    with pytest.raises(EtatManquantError):
        await pipeline.selectionner_meilleur_candidat(state, None)


# --- Pas de fuite d'état d'une adresse à l'autre ---


@pytest.mark.asyncio
async def test_regeocoder_repart_de_zero(monkeypatch, patch_output_dir):
    _patch_clients(monkeypatch, distance_m=150.0)
    state = get_state("e2e-regeocodage")

    geocodage1 = await pipeline.geocoder_entree(state, None, ADRESSE)
    await pipeline.recuperer_reseau_bt(state, None, geocodage1["lat"], geocodage1["lon"])
    await pipeline.recuperer_reseau_routier(state, None, geocodage1["lat"], geocodage1["lon"])
    pipeline.filtrer_candidats_accessibles(state)
    assert state.stage is Stage.CANDIDATS_FILTRES
    assert state.reseau_bt != []
    assert state.candidats != []

    await pipeline.geocoder_entree(state, None, "2 rue Autre, 63000 Clermont-Ferrand")

    assert state.stage is Stage.GEOCODED
    assert state.reseau_bt == []
    assert state.reseau_routier == []
    assert state.candidats == []
    assert state.resultat is None


# --- Aucun candidat accessible ---


@pytest.mark.asyncio
async def test_aucun_candidat_leve_mcp_irve_error(monkeypatch):
    monkeypatch.setattr(pipeline.ban_client, "geocoder_adresse", _make_fake_geocoder())
    monkeypatch.setattr(
        pipeline.enedis_client, "recuperer_troncons", fake_recuperer_troncons_lointains
    )
    monkeypatch.setattr(
        pipeline.geoplateforme_client, "recuperer_routes", fake_recuperer_routes_proches
    )

    state = get_state("e2e-aucun-candidat")
    geocodage = await pipeline.geocoder_entree(state, None, ADRESSE)
    await pipeline.recuperer_reseau_bt(state, None, geocodage["lat"], geocodage["lon"])
    await pipeline.recuperer_reseau_routier(state, None, geocodage["lat"], geocodage["lon"])
    candidats_res = pipeline.filtrer_candidats_accessibles(state)
    assert candidats_res["nb_candidats_retenus"] == 0
    assert state.candidats == []

    with pytest.raises(MCPIrveError, match="buffer_accessibilite_m"):
        await pipeline.selectionner_meilleur_candidat(state, None)
