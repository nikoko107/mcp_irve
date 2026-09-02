import dataclasses

import httpx
import pytest
from shapely.geometry import LineString

from mcp_irve.clients import enedis as enedis_module
from mcp_irve.clients.enedis import recuperer_troncons
from mcp_irve.config import SETTINGS
from mcp_irve.errors import ExternalApiError


@pytest.mark.respx(base_url=SETTINGS.enedis_base_url)
async def test_recuperer_troncons_returns_aerien_and_souterrain(respx_mock, load_fixture):
    respx_mock.get(f"/{SETTINGS.enedis_dataset_aerien}/records").mock(
        return_value=httpx.Response(200, json=load_fixture("enedis_reseau_bt_page1.json"))
    )
    respx_mock.get(f"/{SETTINGS.enedis_dataset_souterrain}/records").mock(
        return_value=httpx.Response(200, json=load_fixture("enedis_reseau_souterrain_bt.json"))
    )

    async with httpx.AsyncClient() as client:
        aeriens, souterrains = await recuperer_troncons(client, 48.853, 2.349, 300)

    assert len(aeriens) == 2
    assert len(souterrains) == 1
    assert all(seg.type == "aerien" for seg in aeriens)
    assert all(seg.type == "souterrain" for seg in souterrains)
    # les ids doivent être uniques et stables (dataset + offset de pagination)
    assert len({seg.id for seg in aeriens}) == 2
    # la géométrie doit être reprojetée en Lambert 93 (grandes coordonnées, pas des degrés)
    assert isinstance(aeriens[0].geometry, LineString)
    x, y = aeriens[0].geometry.coords[0]
    assert x > 100_000
    assert y > 6_000_000
    # la clé "geometry" (chaîne JSON brute) ne doit pas polluer les attributs
    assert "geometry" not in aeriens[0].attributes
    assert aeriens[0].attributes["code_iris"] == "751010101"


@pytest.mark.respx(base_url=SETTINGS.enedis_base_url)
async def test_recuperer_troncons_paginates_until_short_page(respx_mock, load_fixture, monkeypatch):
    small_settings = dataclasses.replace(SETTINGS, enedis_page_size=2, enedis_max_records=10)
    monkeypatch.setattr(enedis_module, "SETTINGS", small_settings)

    page1 = load_fixture("enedis_reseau_bt_page1.json")  # 2 résultats = une page pleine
    page2 = {"total_count": 3, "results": [page1["results"][0]]}  # page courte -> arrêt

    route = respx_mock.get(f"/{SETTINGS.enedis_dataset_aerien}/records")
    route.side_effect = [
        httpx.Response(200, json=page1),
        httpx.Response(200, json=page2),
    ]
    respx_mock.get(f"/{SETTINGS.enedis_dataset_souterrain}/records").mock(
        return_value=httpx.Response(200, json={"total_count": 0, "results": []})
    )

    async with httpx.AsyncClient() as client:
        aeriens, _ = await recuperer_troncons(client, 48.853, 2.349, 300)

    assert route.call_count == 2
    assert len(aeriens) == 3  # 2 (page pleine) + 1 (page courte, arrêt de la pagination)
    # ids stables même en pagination : offset intégré dans l'id
    assert {seg.id for seg in aeriens} == {
        f"{SETTINGS.enedis_dataset_aerien}-0",
        f"{SETTINGS.enedis_dataset_aerien}-1",
        f"{SETTINGS.enedis_dataset_aerien}-2",
    }


@pytest.mark.respx(base_url=SETTINGS.enedis_base_url)
async def test_recuperer_troncons_raises_external_api_error_on_http_failure(respx_mock):
    # recuperer_troncons interroge l'aérien avant le souterrain et lève dès le premier
    # échec : le souterrain n'est jamais appelé, pas besoin de le mocker.
    respx_mock.get(f"/{SETTINGS.enedis_dataset_aerien}/records").mock(
        return_value=httpx.Response(503)
    )

    async with httpx.AsyncClient() as client:
        with pytest.raises(ExternalApiError):
            await recuperer_troncons(client, 48.853, 2.349, 300)
