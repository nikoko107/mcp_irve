"""Serveur MCP — câblage des 9 outils sur la logique de `pipeline.py`.

Chaque outil est un wrapper mince : il récupère l'état de session et le client HTTP
partagé, délègue à la fonction `pipeline.*` correspondante, et reconvertit toute
`MCPIrveError` en `ToolError`. Cette reconversion est nécessaire avec le SDK MCP
installé (mcp 2.x) : seules les `ToolError`/`ResourceError` gardent leur message
d'origine côté client, toute autre exception est remplacée par un message générique
("Error executing tool <name>") pour ne pas exposer d'internals — ce qui effacerait
les messages actionnables rédigés pour le modèle appelant (voir errors.py, state.py).

`pipeline.py` reste volontairement indépendant de `mcp` : c'est ce module qui fait le
pont, pas l'inverse — l'orchestrateur `analyser_raccordement` appelle directement les
fonctions de `pipeline.py`, sans repasser par cette couche.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import pipeline
from .clients.http import create_http_client
from .errors import MCPIrveError
from .state import get_state


@dataclass
class AppContext:
    http: httpx.AsyncClient


@asynccontextmanager
async def _lifespan(_server: MCPServer) -> AsyncIterator[AppContext]:
    async with create_http_client() as http:
        yield AppContext(http=http)


mcp = MCPServer(
    "mcp-irve",
    title="Raccordement IRVE — distance au réseau BT Enedis",
    lifespan=_lifespan,
)


def _http(ctx: Context) -> httpx.AsyncClient:
    # `Context.lifespan` (mcp.server.context.Context) is not the class this SDK
    # version injects into tool functions — the real `Context`
    # (mcp.server.mcpserver.Context) exposes the lifespan output only via
    # `request_context.lifespan_context`, confirmed against the installed mcp 2.x SDK.
    return ctx.request_context.lifespan_context.http


async def _call(coro: Any) -> Any:
    try:
        return await coro
    except MCPIrveError as exc:
        raise ToolError(str(exc)) from exc


def _call_sync(fn: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return fn(*args, **kwargs)
    except MCPIrveError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
async def geocoder_entree(ctx: Context, saisie: str) -> dict:
    """Détecte adresse texte vs coordonnées Google Maps collées, géocode (API BAN) ou
    parse en conséquence. À appeler en premier."""
    state = get_state("default")
    return await _call(pipeline.geocoder_entree(state, _http(ctx), saisie))


@mcp.tool()
async def recuperer_reseau_bt(ctx: Context, lat: float, lon: float, rayon_m: int = 300) -> dict:
    """Récupère le réseau BT Enedis (aérien + souterrain) autour du point, dans un
    rayon de recherche donné. Nécessite d'avoir appelé geocoder_entree au préalable."""
    state = get_state("default")
    return await _call(pipeline.recuperer_reseau_bt(state, _http(ctx), lat, lon, rayon_m))


@mcp.tool()
async def recuperer_reseau_routier(
    ctx: Context, lat: float, lon: float, rayon_m: int = 300
) -> dict:
    """Récupère le réseau routier BD TOPO® (routes/chemins) autour du point, dans le
    même rayon que recuperer_reseau_bt."""
    state = get_state("default")
    return await _call(pipeline.recuperer_reseau_routier(state, _http(ctx), lat, lon, rayon_m))


@mcp.tool()
def filtrer_candidats_accessibles(buffer_m: int = 10) -> dict:
    """Buffer autour du réseau BT, intersection avec le réseau routier, découpe des
    tronçons routiers partiellement inclus. Nécessite reseau BT et réseau routier."""
    state = get_state("default")
    return _call_sync(pipeline.filtrer_candidats_accessibles, state, buffer_m)


@mcp.tool()
async def selectionner_meilleur_candidat(ctx: Context, n_plus_proches: int = 5) -> dict:
    """Présélection à vol d'oiseau des n candidats les plus proches, calcul
    d'itinéraire routier IGN pour chacun, sélection du minimum, comparaison au seuil
    d'éligibilité (200 m par défaut)."""
    state = get_state("default")
    return await _call(pipeline.selectionner_meilleur_candidat(state, _http(ctx), n_plus_proches))


@mcp.tool()
def generer_carte(format: str = "html") -> dict:
    """Génère la carte interactive OpenLayers (Lambert 93) avec les couches du
    résultat. Nécessite qu'un résultat ait été sélectionné."""
    state = get_state("default")
    return _call_sync(pipeline.generer_carte, state, format)


@mcp.tool()
def exporter_geojson(niveau: str = "resultat") -> dict:
    """Exporte le résultat (niveau="resultat") ou l'ensemble des couches utilisées
    (niveau="complet") au format GeoJSON (WGS84)."""
    state = get_state("default")
    return _call_sync(pipeline.exporter_geojson, state, niveau)


@mcp.tool()
def generer_rapport_pdf() -> dict:
    """Génère le rapport PDF (adresse, tronçon retenu, distances, éligibilité, mises
    en garde) à partir du résultat en mémoire. Nécessite qu'un résultat ait été
    sélectionné."""
    state = get_state("default")
    return _call_sync(pipeline.generer_rapport_pdf, state)


@mcp.tool()
async def analyser_raccordement(
    ctx: Context,
    saisie: str,
    rayon_recherche_m: int = 300,
    buffer_accessibilite_m: int = 10,
    n_plus_proches: int = 5,
    generer_carte: bool = True,
    generer_pdf: bool = True,
    generer_geojson: bool = False,
) -> dict:
    """Orchestrateur : enchaîne géocodage, récupération des réseaux BT et routier,
    filtrage d'accessibilité, sélection du meilleur candidat, puis génère carte/PDF/
    GeoJSON selon les options demandées. Point d'entrée recommandé pour l'usage
    courant (un seul appel plutôt que d'enchaîner les outils un par un)."""
    state = get_state("default")
    return await _call(
        pipeline.analyser_raccordement(
            state,
            _http(ctx),
            saisie,
            rayon_recherche_m=rayon_recherche_m,
            buffer_accessibilite_m=buffer_accessibilite_m,
            n_plus_proches=n_plus_proches,
            generer_carte_flag=generer_carte,
            generer_pdf_flag=generer_pdf,
            generer_geojson_flag=generer_geojson,
        )
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
