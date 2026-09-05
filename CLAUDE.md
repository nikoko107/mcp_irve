# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commandes

`uv` gère l'environnement (`pip install --user uv` si absent, puis `export PATH="$HOME/Library/Python/3.14/bin:$PATH"` sur cette machine).

- Installer les dépendances : `uv sync --group dev`
- Lancer le serveur MCP (stdio) : `uv run mcp-irve` ou `uv run python -m mcp_irve.server`
- Tests : `uv run pytest` (un fichier : `uv run pytest tests/geo/test_accessibility.py -v` ; un test : `... -k nom_du_test`)
- Lint : `uv run ruff check .` — format : `uv run ruff format .`

Aucun appel réseau réel dans les tests (tout est mocké avec `respx` ou en monkeypatchant les fonctions clientes) ; les fixtures JSON de référence sont dans `tests/fixtures/`, capturées depuis les vraies APIs.

## Projet

Serveur MCP « MCP Raccordement IRVE » : détermine si un point de raccordement de borne de recharge (IRVE) est éligible au réseau basse tension (BT) Enedis, sur la base d'un seuil de distance **routière** de 200 m (`SETTINGS.seuil_eligibilite_m`, comparaison `<=`). Voir `mcp-raccordement-irve.md` pour le cahier des charges d'origine.

**Principe central : tout le calcul géométrique reste côté serveur.** Les outils MCP ne renvoient que des synthèses numériques et des chemins de fichiers — jamais de géométrie brute. `pipeline.py` reste volontairement indépendant du SDK `mcp` ; c'est `server.py` qui fait le pont (voir plus bas).

## Architecture

```
src/mcp_irve/
  server.py      # 9 outils @mcp.tool(), lifespan (client httpx partagé), traduction MCPIrveError -> ToolError
  pipeline.py     # logique des 9 outils, sans dépendance à `mcp` — server.py ET analyser_raccordement l'appellent
  state.py         # SessionState + Stage (machine d'état linéaire), get_state(), require_stage()
  config.py         # SETTINGS (dataclass frozen) : seuils par défaut, URLs API, projections, output_dir
  models.py          # dataclasses du pipeline (géométries shapely en Lambert 93)
  clients/            # ban.py, enedis.py, geoplateforme.py — un client HTTP par API externe
  geo/                  # projections, accessibility (buffer/intersection), candidates (classement), parsing
  outputs/                # map.py (HTML/OpenLayers), geojson_export.py, pdf_report.py
templates/map.html.j2      # carte OpenLayers, en dehors de src/ (chemin résolu via SETTINGS.templates_dir)
```

### Pipeline à état (9 outils, ordre imposé)

`geocoder_entree → recuperer_reseau_bt / recuperer_reseau_routier → filtrer_candidats_accessibles → selectionner_meilleur_candidat → generer_carte / exporter_geojson / generer_rapport_pdf`, plus `analyser_raccordement` qui enchaîne tout. `state.py::Stage` est un `IntEnum` linéaire ; chaque outil appelle `require_stage()` en préambule et lève `EtatManquantError` si l'étape préalable manque — ce message doit rester actionnable, il est ce que voit le modèle appelant. `geocoder_entree` appelle `state.reset()` avant de géocoder, pour qu'une deuxième adresse dans la même session ne laisse pas de données périmées. Un `asyncio.Lock` par session sérialise les mutations d'état (pas de ré-entrance : ne jamais acquérir le lock d'un outil pendant qu'on tient déjà celui d'un autre appelé depuis le même outil).

L'état est stocké dans `state.py::_STATES`, indexé par `session_id` (`"default"` en pratique, le transport stdio ne servant qu'un client par process) — `server.py` utilise systématiquement `get_state("default")`.

### Décision retenue pour `filtrer_candidats_accessibles`

Lecture **littérale** du cahier des charges (tranchée explicitement avec l'utilisateur, ne pas la reconsidérer sans une nouvelle instruction) : on bufferise le réseau **BT**, on intersecte avec le réseau **routier**, et on découpe les tronçons **routiers** partiellement inclus dans ce buffer. Un `CandidateSegment.type` est donc la nature BD TOPO du tronçon routier (route, chemin...), **pas** une distinction aérien/souterrain. `point_raccordement` est le point sur le segment routier candidat le plus proche du départ — pas un point sur le câble BT lui-même.

**Mise à jour (nouvelle instruction utilisateur) : la distance d'éligibilité va désormais jusqu'au réseau, pas seulement jusqu'à la route.** Le premier constat sur le terrain (carte HTML) : le `point_raccordement` pouvait s'afficher visuellement loin de tout tronçon BT visible, parce que la distance comparée au seuil ne couvrait que le trajet piéton jusqu'à la route candidate — le dernier tronçon route -> câble BT réel (≤ `buffer_m`) était explicitement exclu. `Resultat.distance_routiere_m` (et `RankedCandidate.distance_routiere_m` utilisé pour classer les candidats) est maintenant la somme de trois tronçons :

1. `distance_premier_troncon_m` : distance à vol d'oiseau entre le point d'analyse saisi et le premier point de la géométrie renvoyée par l'itinéraire IGN. Le point d'analyse n'est pas toujours situé exactement sur une route (immeuble, place...) : l'API de routage IGN projette alors silencieusement la requête sur le point routable le plus proche de son propre graphe avant de calculer l'itinéraire — un écart que `itineraire.distance_m` ne couvre pas, et qui restait invisible sur la carte HTML (l'itinéraire, lui, commence déjà sur la voirie). Calculé dans `pipeline.py` (pas une fonction dédiée : simple distance au premier point de `itineraire.geometry`), affiché sur la carte comme une petite ligne pointillée neutre (couche `acces_voirie`, ajoutée par `outputs/_shared.py::construire_features`) et dans le rapport PDF ("Distance du point d'analyse à la route la plus proche").
2. `distance_itineraire_m` : trajet piéton IGN départ -> point_raccordement, inchangé.
3. `distance_dernier_troncon_m` : distance à vol d'oiseau point_raccordement -> câble BT le plus proche (`geo/candidates.py::distance_au_reseau_bt`, toujours ≤ `buffer_m` par construction).

C'est ce total qui est comparé à `SETTINGS.seuil_eligibilite_m` et qui sélectionne le meilleur candidat parmi les `n_plus_proches`. La répartition par type de voie (`geo/itineraire.py`) reçoit en plus les seaux `ACCES_VOIRIE` et `RACCORDEMENT_RESEAU_BT` pour ces deux tronçons hors voirie, ajoutés après coup par `pipeline.py` (hors périmètre de `repartir_longueur_par_type`, qui ne couvre que l'itinéraire routier lui-même).

La zone tampon elle-même (union des buffers `buffer_m` autour du réseau BT) est calculée par `geo/accessibility.py::buffer_reseau_bt` — appelée une fois en interne par `filtrer_candidats`, et une seconde fois par `pipeline.py::filtrer_candidats_accessibles` pour la conserver dans `state.buffer_zone`/`state.buffer_m` (affichage carte + export GeoJSON complet). Duplication de calcul assumée (coût négligeable) pour ne pas changer la signature publique de `filtrer_candidats`.

### Piège cwd du processus (Claude Desktop notamment)

`SETTINGS.output_dir` et `SETTINGS.templates_dir` sont ancrés sur le dossier du projet (`_PROJECT_ROOT`, calculé depuis `__file__`), **jamais** sur un chemin relatif du type `Path("./output")`. Un client MCP peut lancer le serveur avec un `cwd` arbitraire — observé en pratique : Claude Desktop le lance avec `cwd="/"`, donc un défaut relatif résolvait vers `/output` (lecture seule sur macOS) et faisait échouer silencieusement `generer_carte`/`generer_rapport_pdf`/`exporter_geojson` avec le message générique `Error executing tool ...` (voir point suivant). Ne jamais réintroduire un chemin par défaut relatif au cwd dans `config.py`.

### Piège SDK `mcp` (2.x) à connaître avant de toucher à `server.py`

`FastMCP` a été renommé `MCPServer` (`from mcp.server.mcpserver import MCPServer, Context`). Deux points non documentés de façon évidente, découverts en testant en direct (flux mémoire `mcp.shared.memory.create_client_server_memory_streams` + `ClientSession`, pas seulement des appels Python directs) :

1. Le client HTTP partagé (lifespan) n'est **pas** accessible via `ctx.lifespan` (cette propriété existe sur `mcp.server.context.Context`, une classe différente, non utilisée par le chemin d'exécution des outils) — il faut passer par `ctx.request_context.lifespan_context.<attribut>`.
2. Seules les exceptions `ToolError`/`ResourceError` gardent leur message d'origine côté client ; toute autre exception devient le message générique `"Error executing tool <name>"` (protection contre la fuite d'internals). C'est pourquoi `server.py::_call`/`_call_sync` reconvertissent systématiquement `MCPIrveError` (et ses sous-classes : `GeocodingError`, `EtatManquantError`, `ExternalApiError`) en `ToolError` — sans ça, les messages actionnables de `state.require_stage()` n'atteindraient jamais le modèle appelant.

### APIs externes — détails vérifiés en direct (pas seulement lus dans la doc)

- **BAN** (`api-adresse.data.gouv.fr/search/`) : keyless, renvoie déjà `x`/`y` en Lambert 93 dans `properties` — ne pas reprojeter, utiliser tel quel.
- **Enedis open data** (`opendata.enedis.fr/api/explore/v2.1/...`, Opendatasoft) : deux datasets, `reseau-bt` (aérien) et `reseau-souterrain-bt` (souterrain). Le filtre géo qui fonctionne est `where=within_distance(geometry, geom'POINT(lon lat)', <rayon>m)` — **`geofilter.distance` (API v1) est accepté sans erreur mais n'a aucun effet**, ne pas s'y fier. `geometry` est une chaîne JSON à parser, pas un objet imbriqué. Pas d'id unique fourni par l'API (id reconstruit à partir du dataset + offset de pagination).
- **IGN Géoplateforme WFS** (`data.geopf.fr/wfs/ows`, `BDTOPO_V3:troncon_de_route`) : géométries 3D (Z=altitude, à aplatir). Piège d'axes : le filtre `BBOX` n'est accepté qu'en ordre **(lon, lat)** avec suffixe explicite `,EPSG:4326` — l'ordre (lat, lon), pourtant nominal pour ce CRS, renvoie silencieusement zéro résultat.
- **IGN Géoplateforme itinéraire** (`data.geopf.fr/navigation/itineraire`) : keyless, limite documentée 5 req/s/IP (`clients/http.py::itineraire_rate_limiter`, token-bucket à 4,5 req/s). Profil par défaut `pedestrian` (pas `car`) pour éviter les restrictions sens-interdit/voie rapide, non pertinentes pour approximer un tracé de tranchée.

### Sorties

- **Carte HTML** (`outputs/map.py` + `templates/map.html.j2`) : OpenLayers + proj4js (EPSG:2154 non natif à OpenLayers). GeoJSON embarqué **inline** dans le HTML (pas de fichier séparé — `fetch()` local est bloqué par CORS en `file://`) ; toute occurrence de `</` dans le JSON embarqué est échappée en `<\/` pour ne pas clore prématurément la balise `<script>`, et l'adresse affichée passe par le filtre Jinja2 `|e` (protection XSS locale, `autoescape=False` globalement pour ne pas casser le JSON). Fond de plan orthophoto IGN (`ORTHOIMAGERY.ORTHOPHOTOS`, WMTS `data.geopf.fr/wmts`) : **ce flux n'existe qu'en EPSG:3857** (vérifié sur la capacité WMTS — un seul `TileMatrixSet`, `PM`/`PM_0_19`), pas en Lambert 93 ; la vue de la carte reste en EPSG:2154 et OpenLayers reprojette les tuiles à la volée (`ol/reproj`, transparent dès que les deux projections sont enregistrées). La zone tampon (`state.buffer_zone`) est une couche polygone parmi les autres, ajoutée en premier dans `construire_features` (niveau="complet") pour dessiner sous les lignes.
  - **Réseau BT + postes de distribution : couche en direct, pas embarquée.** `construire_features(..., inclure_reseau_bt=False)` dans `map.py` exclut `bt_aerien`/`bt_souterrain` du GeoJSON embarqué (toujours inclus par défaut pour `exporter_geojson`, lui non affecté) ; la carte les recharge en JS à chaque `moveend` (debounce 400 ms) directement depuis l'API Enedis (`opendata.enedis.fr`, CORS `*` — confirmé y compris pour `Origin: null`, donc utilisable depuis un fichier `file://`), dans un rayon calculé sur l'étendue de vue courante (plafonné à `RAYON_MAX_RESEAU_DIRECT_M`). Postes de distribution : dataset `poste-electrique` (976k points nationalement, mêmes conventions que `reseau-bt`). **Piège vérifié en direct : l'API Opendatasoft d'Enedis plafonne strictement `limit` à 100 — une valeur supérieure renvoie HTTP 400**, pas juste une troncature silencieuse ; `NB_MAX_ENREGISTREMENTS` dans le template doit rester ≤ 100 (pas de pagination côté navigateur, affichage "best effort").
- **Export GeoJSON** (`outputs/geojson_export.py`) : toujours reprojeté en WGS84 (RFC 7946). `niveau="complet"` = une seule `FeatureCollection` avec une propriété `layer` par feature plutôt que plusieurs fichiers.
- **PDF** (`outputs/pdf_report.py`, reportlab) : n'utiliser que des caractères Latin-1/WinAnsi dans le texte (la police Helvetica standard non embarquée ne rend pas correctement les caractères hors de cette plage, ex. `≠` — préférer une reformulation). `MISES_EN_GARDE` (3 phrases) est un contrat avec le cahier des charges : toute modification doit les préserver, un test dédié vérifie leur présence par extraction de texte.
- **Répartition de la distance routière par type de voie** (`geo/itineraire.py::repartir_longueur_par_type`, `Resultat.repartition_type_m`) : la ressource de routage IGN (`bdtopo-osrm`) route sur le même référentiel BD TOPO® que le WFS, donc la géométrie de l'itinéraire coïncide (hors rognage aux deux extrémités) avec les tronçons de `state.reseau_routier` — on attribue la longueur par intersection avec chaque tronçon bufferisé de `SETTINGS.repartition_type_tolerance_m` (2 m par défaut). Approximatif par construction : les tolérances de deux tronçons adjacents se chevauchent aux jonctions (quelques mètres comptés en double, négligeable), et toute portion hors du réseau routier récupéré (hors rayon de recherche) tombe dans le seau `TYPE_NON_IDENTIFIE`. Affiché dans le rapport PDF (nouvelle table, seulement si non vide) et dans la légende de la carte HTML (`repartition_type_m` passé au template) ; ajouté aussi comme propriété de la feature `itineraire` dans `outputs/_shared.py::construire_features`, donc présent dans l'export GeoJSON complet.

## Sous-agent de test

`.claude/agents/test-runner.md` : sous-agent dédié à l'écriture/exécution des tests de ce projet (conventions détaillées dans ce fichier). À invoquer après l'implémentation d'un nouveau module plutôt que d'écrire les tests inline.
