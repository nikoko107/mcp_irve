# MCP Raccordement IRVE — Distance au réseau BT Enedis

## Objectif

Serveur MCP permettant, à partir d'une adresse ou de coordonnées, de déterminer l'éligibilité d'un point de raccordement de borne de recharge (IRVE) au réseau BT Enedis, sur la base d'un seuil de distance routière de 200 m.

## Principe général

Tous les traitements géométriques et numériques (buffers, intersections, distances, tris) sont exécutés côté serveur en Python. Le modèle ne reçoit jamais les géométries brutes ni les résultats intermédiaires détaillés — uniquement des synthèses numériques et des chemins de fichiers.

## Méthode de calcul

1. **Entrée** : adresse texte ou coordonnées copiées depuis Google Maps (WGS84, format `lat, lon`).
2. **Géocodage** : API BAN si adresse texte ; parsing direct si coordonnées.
3. **Récupération réseau BT Enedis** : jeux de données ouverts Enedis, réseau aérien + souterrain, dans un rayon de recherche autour du point.
4. **Récupération réseau routier** : API BD TOPO® (routes et chemins) dans la même zone.
5. **Filtrage d'accessibilité** : buffer de 10 m max autour du réseau BT, intersection avec le réseau routier. Découpage des tronçons partiellement inclus (ne garder que la portion dans le buffer). Un tronçon peut produire plusieurs segments candidats disjoints.
6. **Présélection** : classement des candidats par distance à vol d'oiseau (point projeté sur le tronçon), conservation des n plus proches (n configurable, défaut 5).
7. **Distance routière réelle** : pour chaque candidat retenu, calcul d'itinéraire via l'API IGN Géoplateforme (réseau BD TOPO®) entre le point de départ et le point candidat. Conservation du minimum.
8. **Décision** : comparaison de la distance routière minimale au seuil de 200 m → éligible / non éligible.

## Sources de données

- Géocodage / géocodage inverse : API BAN (api-adresse.data.gouv.fr)
- Réseau BT (aérien + souterrain) : jeux de données ouverts Enedis
- Réseau routier : API BD TOPO® / API Géoplateforme IGN
- Calcul d'itinéraire : API Géoplateforme IGN (itinéraire sur réseau routier BD TOPO®)
- Projection de travail pour les calculs géométriques et l'affichage carte : Lambert 93 (EPSG:2154)

## Sorties disponibles

- Synthèse textuelle (distance, éligibilité, tronçon retenu) → renvoyée au modèle
- Carte interactive HTML (OpenLayers, projection Lambert 93) : point de départ, tronçon retenu, candidats secondaires, itinéraire routier, couches BT/routes
- Export GeoJSON (résultat seul ou jeu complet des couches utilisées)
- Rapport PDF : adresse et coordonnées (WGS84 + Lambert 93), tronçon retenu (id, type, longueur), distance à vol d'oiseau, distance routière, statut d'éligibilité, mention des limites de fiabilité (données Enedis déclaratives, distance routière ≠ tracé de tranchée réel)

## Outils MCP

### 1. `geocoder_entree`
- **Entrée** : `saisie: str`
- **Sortie** : `{lat, lon, adresse_normalisee, source}` (`source` = `"BAN"` ou `"coordonnees_directes"`)
- **Rôle** : détecte adresse texte vs coordonnées Google, géocode ou parse en conséquence.

### 2. `recuperer_reseau_bt`
- **Entrée** : `lat: float, lon: float, rayon_m: int = 300`
- **Sortie** : `{nb_troncons_aeriens, nb_troncons_souterrains}`
- **Rôle** : requête réseau BT Enedis (aérien + souterrain) autour du point. Géométries conservées en mémoire serveur.

### 3. `recuperer_reseau_routier`
- **Entrée** : `lat: float, lon: float, rayon_m: int = 300`
- **Sortie** : `{nb_troncons_routes}`
- **Rôle** : requête BD TOPO® (routes/chemins) autour du point.

### 4. `filtrer_candidats_accessibles`
- **Entrée** : `buffer_m: int = 10`
- **Sortie** : `{nb_candidats_retenus}`
- **Rôle** : buffer sur réseau BT, intersection avec routes, découpe des tronçons partiellement inclus.

### 5. `selectionner_meilleur_candidat`
- **Entrée** : `n_plus_proches: int = 5`
- **Sortie** : `{troncon_id, type, distance_vol_oiseau_m, distance_routiere_m, point_raccordement: {lat, lon}, eligible: bool}`
- **Rôle** : présélection à vol d'oiseau, calcul d'itinéraire sur les n candidats, sélection du minimum, comparaison au seuil.

### 6. `generer_carte`
- **Entrée** : `format: str = "html"`
- **Sortie** : `{chemin_fichier}`
- **Rôle** : génère la carte OpenLayers (Lambert 93) avec les couches du résultat.

### 7. `exporter_geojson`
- **Entrée** : `niveau: str = "resultat"` (`"resultat"` ou `"complet"`)
- **Sortie** : `{chemin_fichier}`

### 8. `generer_rapport_pdf`
- **Entrée** : aucun (utilise le résultat en mémoire)
- **Sortie** : `{chemin_fichier}`

### 9. `analyser_raccordement` (orchestrateur)
- **Entrée** : `saisie: str, rayon_recherche_m: int = 300, buffer_accessibilite_m: int = 10, n_plus_proches: int = 5, generer_carte: bool = True, generer_pdf: bool = True, generer_geojson: bool = False`
- **Sortie** : `{adresse_normalisee, distance_routiere_m, eligible, chemins_fichiers: {carte, pdf, geojson?}}`
- **Rôle** : enchaîne les outils 1 à 6 (et 7/8 selon options demandées) en un seul appel, pour l'usage courant.

## Points de vigilance à documenter dans le rapport

- Les données réseau BT Enedis en open data sont déclaratives, non garanties exhaustives ni à jour en temps réel.
- La distance routière calculée est une approximation de la distance de raccordement réelle (tracé de voirie ≠ tracé de tranchée/génie civil).
- Le seuil de 200 m est appliqué sur la distance routière, pas à vol d'oiseau.
