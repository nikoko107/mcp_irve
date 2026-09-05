"""Logique des 9 outils, indépendante de FastMCP.

Chaque fonction ci-dessous correspond à un outil MCP et est appelée à la fois par le
wrapper `@mcp.tool()` correspondant dans `server.py` et par `analyser_raccordement`
(l'orchestrateur), qui les enchaîne directement sans repasser par la couche FastMCP.

Toutes ne renvoient que des dictionnaires de synthèse numérique / chemins de fichiers —
jamais de géométrie brute — conformément au principe central du serveur (voir
mcp-raccordement-irve.md).
"""

from __future__ import annotations

import httpx
from shapely.geometry import Point

from .clients import ban as ban_client
from .clients import enedis as enedis_client
from .clients import geoplateforme as geoplateforme_client
from .config import SETTINGS
from .errors import MCPIrveError
from .geo import accessibility, candidates, parsing
from .geo import itineraire as itineraire_geo
from .geo.projections import l93_to_wgs84, to_point_geo
from .models import PointGeo, Resultat
from .outputs import geojson_export, pdf_report
from .outputs import map as map_output
from .state import SessionState, Stage, require_stage


async def geocoder_entree(state: SessionState, http: httpx.AsyncClient, saisie: str) -> dict:
    async with state.lock:
        state.reset()

        if parsing.detect_saisie_type(saisie) == "coordonnees":
            lat, lon = parsing.parse_coordonnees(saisie)
            point = to_point_geo(lat, lon)
            adresse = saisie.strip()
            source = "coordonnees_directes"
        else:
            point, adresse = await ban_client.geocoder_adresse(http, saisie)
            source = "BAN"

        state.point_depart = point
        state.adresse_normalisee = adresse
        state.saisie_source = source
        state.stage = Stage.GEOCODED

    return {
        "lat": point.lat,
        "lon": point.lon,
        "adresse_normalisee": adresse,
        "source": source,
    }


async def recuperer_reseau_bt(
    state: SessionState, http: httpx.AsyncClient, lat: float, lon: float, rayon_m: int = 300
) -> dict:
    async with state.lock:
        require_stage(state, Stage.GEOCODED)
        aeriens, souterrains = await enedis_client.recuperer_troncons(http, lat, lon, rayon_m)
        state.reseau_bt = aeriens + souterrains
        state.stage = max(state.stage, Stage.RESEAU_BT)

    return {"nb_troncons_aeriens": len(aeriens), "nb_troncons_souterrains": len(souterrains)}


async def recuperer_reseau_routier(
    state: SessionState, http: httpx.AsyncClient, lat: float, lon: float, rayon_m: int = 300
) -> dict:
    async with state.lock:
        require_stage(state, Stage.GEOCODED)
        routes = await geoplateforme_client.recuperer_routes(http, lat, lon, rayon_m)
        state.reseau_routier = routes
        state.stage = max(state.stage, Stage.RESEAU_ROUTIER)

    return {"nb_troncons_routes": len(routes)}


def filtrer_candidats_accessibles(state: SessionState, buffer_m: int = 10) -> dict:
    require_stage(state, Stage.RESEAU_ROUTIER)
    candidats = accessibility.filtrer_candidats(state.reseau_bt, state.reseau_routier, buffer_m)
    state.candidats = candidats
    state.buffer_m = buffer_m
    state.buffer_zone = accessibility.buffer_reseau_bt(state.reseau_bt, buffer_m)
    state.stage = max(state.stage, Stage.CANDIDATS_FILTRES)
    return {"nb_candidats_retenus": len(candidats)}


async def selectionner_meilleur_candidat(
    state: SessionState, http: httpx.AsyncClient, n_plus_proches: int = 5
) -> dict:
    async with state.lock:
        require_stage(state, Stage.CANDIDATS_FILTRES)
        if not state.candidats:
            raise MCPIrveError(
                "Aucun candidat accessible trouvé — élargir rayon_recherche_m ou "
                "buffer_accessibilite_m avant de relancer le pipeline."
            )
        assert state.point_depart is not None  # garanti par require_stage(GEOCODED) en amont

        point_depart_l93 = Point(state.point_depart.x_l93, state.point_depart.y_l93)
        ranked = candidates.selectionner_n_plus_proches(
            candidates.classer_candidats(point_depart_l93, state.candidats), n_plus_proches
        )

        best = None
        for rc in ranked:
            lat_c, lon_c = l93_to_wgs84(rc.point_le_plus_proche.x, rc.point_le_plus_proche.y)
            itineraire = await geoplateforme_client.calculer_itineraire(
                http, state.point_depart.lat, state.point_depart.lon, lat_c, lon_c
            )
            # Distance totale départ -> réseau BT : premier tronçon (point d'analyse ->
            # point réellement pris comme origine par l'itinéraire IGN — le point saisi
            # n'est pas toujours sur une route) + itinéraire piéton jusqu'à la route
            # candidate + dernier tronçon (route -> câble BT réel, non couvert par la
            # voirie). Le classement et la comparaison au seuil portent sur ce total, pas
            # sur le seul tronçon de voirie — sans quoi la distance affichée sous-estime
            # systématiquement la distance réelle jusqu'au réseau.
            rc.distance_premier_troncon_m = (
                point_depart_l93.distance(Point(itineraire.geometry.coords[0]))
                if itineraire.geometry is not None
                else 0.0
            )
            rc.distance_dernier_troncon_m = candidates.distance_au_reseau_bt(
                rc.point_le_plus_proche, state.reseau_bt
            )
            rc.distance_routiere_m = (
                rc.distance_premier_troncon_m
                + itineraire.distance_m
                + rc.distance_dernier_troncon_m
            )
            if best is None or rc.distance_routiere_m < best[0].distance_routiere_m:
                best = (rc, itineraire)

        # ranked non vide : state.candidats non vide (vérifié ci-dessus) et n_plus_proches >= 1
        assert best is not None
        best_candidate, best_itineraire = best

        # Le point de raccordement est le point sur le câble BT réel, pas sur la route :
        # la route n'est qu'un point de passage pour l'itinéraire, le raccordement se
        # fait physiquement sur le réseau électrique.
        point_sur_reseau_bt = candidates.point_le_plus_proche_reseau_bt(
            best_candidate.point_le_plus_proche, state.reseau_bt
        )
        lat_pt, lon_pt = l93_to_wgs84(point_sur_reseau_bt.x, point_sur_reseau_bt.y)
        point_raccordement = PointGeo(
            lat=lat_pt,
            lon=lon_pt,
            x_l93=point_sur_reseau_bt.x,
            y_l93=point_sur_reseau_bt.y,
        )
        dans_perimetre_analyse = best_candidate.distance_routiere_m <= SETTINGS.perimetre_analyse_m

        repartition_type_m: dict[str, float] = {}
        if best_itineraire.geometry is not None:
            repartition_type_m = itineraire_geo.repartir_longueur_par_type(
                best_itineraire.geometry,
                state.reseau_routier,
                SETTINGS.repartition_type_tolerance_m,
            )
        if best_candidate.distance_dernier_troncon_m:
            repartition_type_m[itineraire_geo.RACCORDEMENT_RESEAU_BT] = (
                best_candidate.distance_dernier_troncon_m
            )
        if best_candidate.distance_premier_troncon_m:
            repartition_type_m[itineraire_geo.ACCES_VOIRIE] = (
                best_candidate.distance_premier_troncon_m
            )
        if best_candidate.distance_dernier_troncon_m or best_candidate.distance_premier_troncon_m:
            repartition_type_m = dict(
                sorted(repartition_type_m.items(), key=lambda item: item[1], reverse=True)
            )

        state.resultat = Resultat(
            troncon_id=best_candidate.candidate.source_troncon_id,
            type=best_candidate.candidate.type,
            distance_vol_oiseau_m=best_candidate.distance_vol_oiseau_m,
            distance_routiere_m=best_candidate.distance_routiere_m,
            point_raccordement=point_raccordement,
            dans_perimetre_analyse=dans_perimetre_analyse,
            candidat=best_candidate.candidate,
            itineraire=best_itineraire,
            distance_premier_troncon_m=best_candidate.distance_premier_troncon_m,
            distance_itineraire_m=best_itineraire.distance_m,
            distance_dernier_troncon_m=best_candidate.distance_dernier_troncon_m,
            repartition_type_m=repartition_type_m,
        )
        state.stage = max(state.stage, Stage.RESULTAT)

    resultat = state.resultat
    return {
        "troncon_id": resultat.troncon_id,
        "type": resultat.type,
        "distance_vol_oiseau_m": round(resultat.distance_vol_oiseau_m, 1),
        "distance_routiere_m": round(resultat.distance_routiere_m, 1),
        "distance_premier_troncon_m": round(resultat.distance_premier_troncon_m, 1),
        "distance_itineraire_m": round(resultat.distance_itineraire_m, 1),
        "distance_dernier_troncon_m": round(resultat.distance_dernier_troncon_m, 1),
        "point_raccordement": {"lat": point_raccordement.lat, "lon": point_raccordement.lon},
        "dans_perimetre_analyse": dans_perimetre_analyse,
        "repartition_type_m": {k: round(v, 1) for k, v in resultat.repartition_type_m.items()},
    }


def generer_carte(state: SessionState, format: str = "html") -> dict:
    require_stage(state, Stage.RESULTAT)
    if format != "html":
        raise MCPIrveError(
            f"Format de carte non supporté : {format!r} (seul 'html' est disponible)."
        )
    chemin = map_output.generer_carte_html(state)
    return {"chemin_fichier": str(chemin)}


def exporter_geojson(state: SessionState, niveau: str = "resultat") -> dict:
    if niveau not in ("resultat", "complet"):
        raise MCPIrveError(f"niveau doit être 'resultat' ou 'complet', reçu : {niveau!r}.")
    require_stage(state, Stage.RESULTAT if niveau == "resultat" else Stage.CANDIDATS_FILTRES)
    chemin = geojson_export.exporter_geojson(state, niveau)
    return {"chemin_fichier": str(chemin)}


def generer_rapport_pdf(state: SessionState) -> dict:
    require_stage(state, Stage.RESULTAT)
    chemin = pdf_report.generer_rapport_pdf(state)
    return {"chemin_fichier": str(chemin)}


async def analyser_raccordement(
    state: SessionState,
    http: httpx.AsyncClient,
    saisie: str,
    rayon_recherche_m: int = 300,
    buffer_accessibilite_m: int = 10,
    n_plus_proches: int = 5,
    generer_carte_flag: bool = True,
    generer_pdf_flag: bool = True,
    generer_geojson_flag: bool = False,
) -> dict:
    """Enchaîne les outils 1 à 6 (et 7/8 selon options) en un seul appel."""
    geocodage = await geocoder_entree(state, http, saisie)
    await recuperer_reseau_bt(state, http, geocodage["lat"], geocodage["lon"], rayon_recherche_m)
    await recuperer_reseau_routier(
        state, http, geocodage["lat"], geocodage["lon"], rayon_recherche_m
    )
    filtrer_candidats_accessibles(state, buffer_accessibilite_m)
    resultat = await selectionner_meilleur_candidat(state, http, n_plus_proches)

    chemins_fichiers: dict[str, str] = {}
    if generer_carte_flag:
        chemins_fichiers["carte"] = generer_carte(state)["chemin_fichier"]
    if generer_pdf_flag:
        chemins_fichiers["pdf"] = generer_rapport_pdf(state)["chemin_fichier"]
    if generer_geojson_flag:
        chemins_fichiers["geojson"] = exporter_geojson(state)["chemin_fichier"]

    return {
        "adresse_normalisee": geocodage["adresse_normalisee"],
        "distance_routiere_m": resultat["distance_routiere_m"],
        "dans_perimetre_analyse": resultat["dans_perimetre_analyse"],
        "chemins_fichiers": chemins_fichiers,
    }
