import httpx
import pytest
from shapely.geometry import LineString

from mcp_irve.clients.geoplateforme import calculer_itineraire, recuperer_routes
from mcp_irve.config import SETTINGS
from mcp_irve.errors import ExternalApiError


@pytest.mark.respx(base_url=SETTINGS.geopf_wfs_url)
async def test_recuperer_routes_parses_features_and_drops_z(respx_mock, load_fixture):
    respx_mock.get("/ows").mock(
        return_value=httpx.Response(200, json=load_fixture("wfs_troncon_de_route.json"))
    )

    async with httpx.AsyncClient() as client:
        routes = await recuperer_routes(client, 48.853, 2.349, 300)

    assert len(routes) == 2
    ids = {r.id for r in routes}
    assert ids == {"TRONROUT0000000001", "TRONROUT0000000002"}
    natures = {r.id: r.nature for r in routes}
    assert natures["TRONROUT0000000001"] == "Route à 1 chaussée"
    assert natures["TRONROUT0000000002"] == "Chemin"

    route = routes[0]
    assert isinstance(route.geometry, LineString)
    # la géométrie source est 3D (Z=altitude) -> doit être aplatie en 2D
    assert not route.geometry.has_z
    # et reprojetée en Lambert 93 (grandes coordonnées, pas des degrés)
    x, y = route.geometry.coords[0]
    assert x > 100_000
    assert y > 6_000_000


@pytest.mark.respx(base_url=SETTINGS.geopf_wfs_url)
async def test_recuperer_routes_raises_on_http_error(respx_mock):
    respx_mock.get("/ows").mock(return_value=httpx.Response(500))

    async with httpx.AsyncClient() as client:
        with pytest.raises(ExternalApiError):
            await recuperer_routes(client, 48.853, 2.349, 300)


@pytest.mark.respx
async def test_calculer_itineraire_parses_distance_and_geometry(respx_mock, load_fixture):
    respx_mock.get(SETTINGS.geopf_itineraire_url).mock(
        return_value=httpx.Response(200, json=load_fixture("itineraire.json"))
    )

    async with httpx.AsyncClient() as client:
        itineraire = await calculer_itineraire(client, 48.853, 2.349, 48.854, 2.35)

    assert itineraire.distance_m == pytest.approx(180.5)
    assert itineraire.duree_s == pytest.approx(150.2)
    assert isinstance(itineraire.geometry, LineString)
    x, y = itineraire.geometry.coords[0]
    assert x > 100_000
    assert y > 6_000_000


@pytest.mark.respx
async def test_calculer_itineraire_raises_on_http_error(respx_mock):
    respx_mock.get(SETTINGS.geopf_itineraire_url).mock(return_value=httpx.Response(500))

    async with httpx.AsyncClient() as client:
        with pytest.raises(ExternalApiError):
            await calculer_itineraire(client, 48.853, 2.349, 48.854, 2.35)
