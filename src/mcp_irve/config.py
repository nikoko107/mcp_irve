"""Paramètres du serveur : valeurs par défaut du pipeline, URLs des APIs externes,
délais et emplacement de sortie des fichiers générés.

Toutes les valeurs sont surchageables par variable d'environnement (préfixe ``MCP_IRVE_``)
pour permettre de pointer vers un environnement de test sans toucher au code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    return float(value) if value else default


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value else default


def _env_str(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    # --- Valeurs par défaut du pipeline ---
    rayon_recherche_m: int = field(
        default_factory=lambda: _env_int("MCP_IRVE_RAYON_RECHERCHE_M", 300)
    )
    buffer_accessibilite_m: int = field(default_factory=lambda: _env_int("MCP_IRVE_BUFFER_M", 10))
    n_plus_proches: int = field(default_factory=lambda: _env_int("MCP_IRVE_N_PLUS_PROCHES", 5))
    seuil_eligibilite_m: float = field(
        default_factory=lambda: _env_float("MCP_IRVE_SEUIL_M", 200.0)
    )
    longueur_min_segment_m: float = 1.0
    """En-deçà de cette longueur, un segment candidat issu de la découpe (effleurement
    tangentiel du buffer) est considéré comme un artefact géométrique et ignoré."""

    # --- Projections ---
    crs_travail: str = "EPSG:2154"  # Lambert 93
    crs_echange: str = "EPSG:4326"  # WGS84

    # --- API BAN (géocodage) ---
    ban_base_url: str = field(default_factory=lambda: _env_str("MCP_IRVE_BAN_URL", "https://api-adresse.data.gouv.fr"))

    # --- Enedis open data (réseau BT) ---
    enedis_base_url: str = field(
        default_factory=lambda: _env_str(
            "MCP_IRVE_ENEDIS_URL", "https://opendata.enedis.fr/api/explore/v2.1/catalog/datasets"
        )
    )
    enedis_dataset_aerien: str = "reseau-bt"
    enedis_dataset_souterrain: str = "reseau-souterrain-bt"
    enedis_dataset_poste: str = "poste-electrique"
    """Postes de distribution HTA/BT — utilisé uniquement côté navigateur (carte HTML,
    couche en direct), jamais par les clients Python : voir templates/map.html.j2."""
    enedis_page_size: int = 100
    enedis_max_records: int = 2000
    """Garde-fou de pagination — le plafond historique de l'API Explore est ~10 000
    lignes par requête ; ceci est une sécurité, pas une limite qu'on s'attend à atteindre
    à un rayon de recherche de quelques centaines de mètres."""

    # --- IGN Géoplateforme (réseau routier BD TOPO + itinéraire) ---
    geopf_wfs_url: str = field(default_factory=lambda: _env_str("MCP_IRVE_GEOPF_WFS_URL", "https://data.geopf.fr/wfs"))
    geopf_wfs_typename: str = "BDTOPO_V3:troncon_de_route"
    geopf_itineraire_url: str = field(
        default_factory=lambda: _env_str(
            "MCP_IRVE_GEOPF_ITINERAIRE_URL", "https://data.geopf.fr/navigation/itineraire"
        )
    )
    geopf_itineraire_resource: str = "bdtopo-osrm"
    geopf_itineraire_profile: str = "pedestrian"
    """Profil piéton par défaut : évite les restrictions "voiture uniquement" (sens
    interdits, voies rapides) qui n'ont pas de sens pour approximer un tracé de tranchée."""
    geopf_itineraire_optimization: str = "fastest"
    geopf_itineraire_rate_limit_per_s: float = 4.5  # limite documentée : 5 req/s/IP

    # --- HTTP ---
    http_timeout_s: float = field(
        default_factory=lambda: _env_float("MCP_IRVE_HTTP_TIMEOUT_S", 15.0)
    )
    http_user_agent: str = "mcp-irve/0.1 (+https://github.com/nikoko107/mcp_irve)"

    # --- Sorties fichiers ---
    # Le défaut est ancré sur le dossier du projet, pas sur le répertoire courant du
    # processus : un client MCP (Claude Desktop notamment) peut lancer le serveur avec
    # un cwd arbitraire (observé : "/", en lecture seule sur macOS), donc un défaut
    # relatif type "./output" résoudrait vers un chemin inexploitable.
    output_dir: Path = field(
        default_factory=lambda: Path(
            _env_str("MCP_IRVE_OUTPUT_DIR", str(_PROJECT_ROOT / "output"))
        )
    )
    templates_dir: Path = field(
        default_factory=lambda: Path(
            _env_str("MCP_IRVE_TEMPLATES_DIR", str(_PROJECT_ROOT / "templates"))
        )
    )


SETTINGS = Settings()
