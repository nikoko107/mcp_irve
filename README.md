# MCP Raccordement IRVE

Serveur [MCP](https://modelcontextprotocol.io) qui détermine, à partir d'une adresse ou de coordonnées, l'éligibilité d'un point de raccordement de borne de recharge (IRVE) au réseau basse tension (BT) Enedis — sur la base d'un seuil de **distance routière** de 200 m (et non à vol d'oiseau).

Tous les traitements géométriques (buffers, intersections, découpes, distances) s'exécutent côté serveur en Python. Le modèle appelant ne reçoit jamais de géométrie brute, seulement des synthèses numériques et des chemins de fichiers vers les artefacts générés (carte, PDF, GeoJSON).

Le cahier des charges complet est dans [`mcp-raccordement-irve.md`](./mcp-raccordement-irve.md). Les décisions d'architecture et pièges connus du SDK sont documentés dans [`CLAUDE.md`](./CLAUDE.md).

## Méthode

1. **Géocodage** de l'entrée (adresse texte via l'API [BAN](https://api-adresse.data.gouv.fr), ou coordonnées `lat, lon` collées depuis Google Maps).
2. **Récupération du réseau BT Enedis** (aérien + souterrain, [open data Enedis](https://opendata.enedis.fr)) et du **réseau routier** ([BD TOPO®](https://geoservices.ign.fr/bdtopo) via l'API [IGN Géoplateforme](https://geoservices.ign.fr/documentation/services/services-geoplateforme)) autour du point.
3. **Filtrage d'accessibilité** : buffer autour du réseau BT, intersection avec les routes, découpe des tronçons routiers partiellement inclus — un tronçon peut produire plusieurs segments candidats disjoints.
4. **Présélection** des candidats les plus proches à vol d'oiseau, puis **calcul d'itinéraire routier réel** (API Géoplateforme) pour chacun ; conservation du minimum.
5. **Décision** : éligible si la distance routière minimale est ≤ 200 m.

## Outils MCP

| Outil | Rôle |
|---|---|
| `geocoder_entree` | Géocode une adresse ou parse des coordonnées |
| `recuperer_reseau_bt` | Récupère le réseau BT Enedis autour du point |
| `recuperer_reseau_routier` | Récupère le réseau routier BD TOPO® autour du point |
| `filtrer_candidats_accessibles` | Filtre les tronçons routiers accessibles depuis le réseau BT |
| `selectionner_meilleur_candidat` | Classe, calcule les itinéraires, sélectionne le meilleur, décide de l'éligibilité |
| `generer_carte` | Génère une carte interactive HTML (OpenLayers, Lambert 93, fond orthophoto IGN, réseau BT et postes de distribution en direct depuis l'API Enedis) |
| `exporter_geojson` | Exporte le résultat ou l'ensemble des couches en GeoJSON |
| `generer_rapport_pdf` | Génère un rapport PDF (adresse, tronçon retenu, distances, éligibilité, limites) |
| `analyser_raccordement` | Orchestrateur : enchaîne tout le pipeline en un seul appel |

## Installation

### Prérequis

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) pour la gestion de l'environnement et des dépendances

Si `uv` n'est pas installé :

```bash
pip3 install --user uv
# puis, si la commande "uv" n'est pas trouvée, ajoutez-la au PATH (macOS) :
export PATH="$HOME/Library/Python/3.<version>/bin:$PATH"
```

(ou via Homebrew : `brew install uv`, si `/opt/homebrew` vous appartient).

> **macOS : évitez `~/Documents`, `~/Desktop` et `~/Downloads`.** Ce sont des dossiers protégés par macOS (TCC) — un client MCP lancé en tant qu'app graphique (Claude Desktop) n'a pas accès à leur contenu par défaut, même s'il arrive à lancer l'exécutable. Symptôme observé : le serveur se connecte puis crashe immédiatement avec `PermissionError: Operation not permitted` dans `~/Library/Logs/Claude/mcp-server-irve.log`. Clonez plutôt le projet directement sous `~` (ex. `~/mcp_irve`) ou ailleurs hors de ces dossiers.

### Installer les dépendances

```bash
cd mcp_irve
uv sync --group dev
```

Ceci crée un environnement virtuel dans `.venv/` avec toutes les dépendances (dont l'exécutable `mcp-irve`, utilisable directement sans passer par `uv run`).

### Vérifier l'installation

```bash
uv run pytest        # doit afficher "83 passed" (aucun appel réseau réel)
uv run mcp-irve       # démarre le serveur en stdio — Ctrl+C pour arrêter
```

## Lancer le serveur / l'ajouter à un client MCP

### Claude Code (CLI)

```bash
claude mcp add irve -s user -- /chemin/absolu/vers/mcp_irve/.venv/bin/mcp-irve
```

`-s user` le rend disponible dans toutes les sessions Claude Code sur la machine (omettez pour le limiter au projet courant). Redémarrez Claude Code ensuite.

### Claude Desktop

Éditez `~/Library/Application Support/Claude/claude_desktop_config.json` (faites une copie avant si le fichier existe déjà et contient d'autres réglages) pour y ajouter :

```json
{
  "mcpServers": {
    "irve": {
      "command": "/chemin/absolu/vers/mcp_irve/.venv/bin/mcp-irve"
    }
  }
}
```

Pointer directement vers le script de l'environnement virtuel (plutôt que vers `uv run --directory ...`) évite toute dépendance au `PATH` de l'app graphique, qui n'hérite pas forcément de celui du shell. Quittez complètement Claude Desktop (⌘Q) et relancez-le pour que le nouveau serveur soit pris en compte.

En cas de souci, les logs du serveur sont dans `~/Library/Logs/Claude/mcp-server-irve.log` (stdout/stderr du process Python) et `~/Library/Logs/Claude/mcp.log` (côté client MCP).

### Configuration

Toutes les valeurs par défaut (`config.py`) sont surchargeables par variable d'environnement, notamment :

- `MCP_IRVE_RAYON_RECHERCHE_M` (défaut 300), `MCP_IRVE_BUFFER_M` (défaut 10), `MCP_IRVE_SEUIL_M` (défaut 200)
- `MCP_IRVE_OUTPUT_DIR` (défaut `./output`) — emplacement des cartes/PDF/GeoJSON générés

## Développement

```bash
uv run pytest              # suite de tests (mockée, aucun appel réseau réel)
uv run ruff check .        # lint
uv run ruff format .       # formatage
```

## Sources de données

- Géocodage : [API BAN](https://api-adresse.data.gouv.fr) (api-adresse.data.gouv.fr)
- Réseau BT Enedis et postes de distribution : [open data Enedis](https://opendata.enedis.fr) (déclaratif, non garanti exhaustif ni temps réel ; postes affichés en direct sur la carte, non utilisés dans le calcul d'éligibilité)
- Réseau routier et itinéraires : [API Géoplateforme IGN](https://geoservices.ign.fr) (BD TOPO®)
- Projection de travail : Lambert 93 / EPSG:2154 ; échanges en WGS84

## Limites

- Les données réseau BT Enedis en open data sont déclaratives, non garanties exhaustives ni à jour en temps réel.
- La distance routière calculée est une approximation de la distance de raccordement réelle (le tracé de voirie n'est pas le tracé de tranchée/génie civil réel).
- Le seuil d'éligibilité de 200 m s'applique à la distance routière, pas à la distance à vol d'oiseau.

## Licence

Non définie.
