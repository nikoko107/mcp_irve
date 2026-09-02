import pytest

from mcp_irve.geo.parsing import detect_saisie_type, parse_coordonnees


@pytest.mark.parametrize(
    "saisie",
    [
        "48.8566, 2.3522",
        "48.8566,2.3522",
        "48.8566 , 2.3522",
        "-48.8566,-2.3522",
        "0,0",
    ],
)
def test_detect_saisie_type_reconnait_les_coordonnees(saisie):
    assert detect_saisie_type(saisie) == "coordonnees"


@pytest.mark.parametrize(
    "saisie",
    [
        "10 rue de la Paix, 75002 Paris",
        "Tour Eiffel",
        "1 avenue Anatole France, 75007 Paris",
        "",
        "48.8566",
    ],
)
def test_detect_saisie_type_reconnait_une_adresse(saisie):
    assert detect_saisie_type(saisie) == "adresse"


def test_parse_coordonnees_extrait_lat_lon():
    lat, lon = parse_coordonnees("48.8566, 2.3522")

    assert lat == pytest.approx(48.8566)
    assert lon == pytest.approx(2.3522)


def test_parse_coordonnees_sans_espace():
    lat, lon = parse_coordonnees("48.8566,2.3522")

    assert lat == pytest.approx(48.8566)
    assert lon == pytest.approx(2.3522)


def test_parse_coordonnees_leve_value_error_si_latitude_hors_bornes():
    with pytest.raises(ValueError):
        parse_coordonnees("95, 2.3522")


def test_parse_coordonnees_leve_value_error_si_longitude_hors_bornes():
    with pytest.raises(ValueError):
        parse_coordonnees("48.8566, 200")


def test_parse_coordonnees_leve_value_error_si_saisie_mal_formee():
    with pytest.raises(ValueError):
        parse_coordonnees("10 rue de la Paix, 75002 Paris")
