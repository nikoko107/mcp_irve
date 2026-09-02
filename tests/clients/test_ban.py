import httpx
import pytest

from mcp_irve.clients.ban import geocoder_adresse
from mcp_irve.config import SETTINGS
from mcp_irve.errors import GeocodingError


@pytest.mark.respx(base_url=SETTINGS.ban_base_url)
async def test_geocoder_adresse_returns_point_and_label(respx_mock, load_fixture):
    respx_mock.get("/search/").mock(
        return_value=httpx.Response(200, json=load_fixture("ban_search.json"))
    )

    async with httpx.AsyncClient() as client:
        point, adresse = await geocoder_adresse(client, "1 rue de rivoli paris")

    assert adresse == "1 Rue de Rivoli 75001 Paris"
    assert point.lat == pytest.approx(48.8534)
    assert point.lon == pytest.approx(2.3492)
    # x_l93/y_l93 doivent venir directement des properties BAN, pas être recalculés
    assert point.x_l93 == pytest.approx(651500.12)
    assert point.y_l93 == pytest.approx(6862300.45)


@pytest.mark.respx(base_url=SETTINGS.ban_base_url)
async def test_geocoder_adresse_raises_when_no_result(respx_mock, load_fixture):
    respx_mock.get("/search/").mock(
        return_value=httpx.Response(200, json=load_fixture("ban_search_empty.json"))
    )

    async with httpx.AsyncClient() as client:
        with pytest.raises(GeocodingError, match="Aucune adresse"):
            await geocoder_adresse(client, "adresse totalement inconnue xyz")


@pytest.mark.respx(base_url=SETTINGS.ban_base_url)
async def test_geocoder_adresse_raises_on_http_error(respx_mock):
    respx_mock.get("/search/").mock(return_value=httpx.Response(500))

    async with httpx.AsyncClient() as client:
        with pytest.raises(GeocodingError):
            await geocoder_adresse(client, "1 rue de rivoli paris")
