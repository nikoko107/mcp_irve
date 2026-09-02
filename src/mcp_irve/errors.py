"""Exceptions du serveur MCP IRVE.

Les messages sont rédigés pour être lus directement par le modèle appelant
(FastMCP remonte le texte de l'exception comme erreur d'outil) : ils doivent
donc rester actionnables, pas seulement descriptifs.
"""


class MCPIrveError(Exception):
    """Racine commune de toutes les erreurs du serveur."""


class GeocodingError(MCPIrveError):
    """La saisie n'a pas pu être géocodée ou interprétée comme des coordonnées."""


class EtatManquantError(MCPIrveError):
    """Un outil a été appelé avant qu'une étape préalable du pipeline n'ait été exécutée."""


class ExternalApiError(MCPIrveError):
    """Une API externe (BAN, Enedis, Géoplateforme) a renvoyé une erreur ou une
    réponse inexploitable."""
