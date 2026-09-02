"""État du pipeline, conservé côté serveur entre les appels d'outils MCP d'une même session.

Le transport stdio du SDK MCP démarre un process par connexion client, donc un
dictionnaire indexé par ``session_id`` (avec une seule clé ``"default"`` en pratique)
suffit aujourd'hui — mais garder la clé explicite évite une réécriture si un transport
HTTP multi-session est ajouté plus tard.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import IntEnum

from shapely.geometry.base import BaseGeometry

from .errors import EtatManquantError
from .models import CandidateSegment, PointGeo, ReseauSegment, Resultat, RouteSegment


class Stage(IntEnum):
    EMPTY = 0
    GEOCODED = 1
    RESEAU_BT = 2
    RESEAU_ROUTIER = 3
    CANDIDATS_FILTRES = 4
    RESULTAT = 5


_STAGE_TOOL_HINT: dict[Stage, str] = {
    Stage.GEOCODED: "geocoder_entree",
    Stage.RESEAU_BT: "recuperer_reseau_bt",
    Stage.RESEAU_ROUTIER: "recuperer_reseau_routier",
    Stage.CANDIDATS_FILTRES: "filtrer_candidats_accessibles",
    Stage.RESULTAT: "selectionner_meilleur_candidat",
}


@dataclass
class SessionState:
    session_id: str = "default"
    version: int = 0
    stage: Stage = Stage.EMPTY
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False, compare=False)

    point_depart: PointGeo | None = None
    adresse_normalisee: str | None = None
    saisie_source: str | None = None  # "BAN" | "coordonnees_directes"

    reseau_bt: list[ReseauSegment] = field(default_factory=list)
    reseau_routier: list[RouteSegment] = field(default_factory=list)
    candidats: list[CandidateSegment] = field(default_factory=list)
    buffer_m: float | None = None
    buffer_zone: BaseGeometry | None = None
    """Union des buffers autour du réseau BT (Lambert 93), calculée par
    filtrer_candidats_accessibles — conservée pour affichage (carte, export complet),
    pas seulement pour son usage interne dans le filtrage des candidats."""
    resultat: Resultat | None = None

    def reset(self) -> None:
        """Invalide tout l'état en aval — appelé par geocoder_entree pour qu'une
        deuxième adresse traitée dans la même session ne laisse pas de données périmées.
        """
        self.version += 1
        self.stage = Stage.EMPTY
        self.point_depart = None
        self.adresse_normalisee = None
        self.saisie_source = None
        self.reseau_bt = []
        self.reseau_routier = []
        self.candidats = []
        self.buffer_m = None
        self.buffer_zone = None
        self.resultat = None


_STATES: dict[str, SessionState] = {}


def get_state(session_id: str = "default") -> SessionState:
    if session_id not in _STATES:
        _STATES[session_id] = SessionState(session_id=session_id)
    return _STATES[session_id]


def require_stage(state: SessionState, minimum: Stage) -> None:
    """Lève EtatManquantError si le pipeline n'a pas encore atteint l'étape ``minimum``.

    Le message nomme l'outil à appeler en premier : FastMCP remonte cette exception
    telle quelle comme erreur d'outil, ce qui rend le modèle appelant auto-correctif.
    """
    if state.stage < minimum:
        outil = _STAGE_TOOL_HINT.get(minimum, minimum.name)
        raise EtatManquantError(
            f"Étape manquante : appelez d'abord l'outil '{outil}' avant de poursuivre "
            f"(étape actuelle : {state.stage.name}, requise : {minimum.name})."
        )
