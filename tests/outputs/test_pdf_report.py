import pdfplumber

from mcp_irve.outputs import pdf_report
from mcp_irve.outputs.pdf_report import MISES_EN_GARDE

from ._helpers import build_state

# Sous-chaînes significatives des trois mises en garde (cf. pdf_report.MISES_EN_GARDE),
# choisies après la puce "•" : pdfplumber extrait parfois ce caractère en "(cid:127)",
# donc on ne cherche jamais la puce elle-même.
assert "données réseau BT Enedis" in MISES_EN_GARDE[0]
assert "s'applique à la distance routière" in MISES_EN_GARDE[2]

SOUS_CHAINES_ATTENDUES = [
    "données réseau BT Enedis",
    "approximation de la distance de",
    "s'applique à la distance routière",
]


def _extract_text(chemin) -> str:
    with pdfplumber.open(str(chemin)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def test_pdf_contient_les_trois_mises_en_garde(patch_output_dir):
    state = build_state(eligible=True)

    chemin = pdf_report.generer_rapport_pdf(state)
    texte = _extract_text(chemin)

    for sous_chaine in SOUS_CHAINES_ATTENDUES:
        assert sous_chaine in texte, f"Mise en garde manquante dans le PDF : {sous_chaine!r}"


def test_pdf_affiche_ladresse_et_le_statut_eligible(patch_output_dir):
    state = build_state(eligible=True)

    chemin = pdf_report.generer_rapport_pdf(state)
    texte = _extract_text(chemin)

    assert state.adresse_normalisee in texte
    assert "ÉLIGIBLE" in texte
    assert "NON ÉLIGIBLE" not in texte


def test_pdf_affiche_le_statut_non_eligible(patch_output_dir):
    state = build_state(eligible=False)

    chemin = pdf_report.generer_rapport_pdf(state)
    texte = _extract_text(chemin)

    assert "NON ÉLIGIBLE" in texte


def test_pdf_affiche_les_distances_arrondies(patch_output_dir):
    state = build_state(eligible=True)
    resultat = state.resultat

    chemin = pdf_report.generer_rapport_pdf(state)
    texte = _extract_text(chemin)

    assert f"{resultat.distance_vol_oiseau_m:.1f} m" in texte
    assert f"{resultat.distance_routiere_m:.1f} m" in texte


def test_pdf_affiche_la_table_repartition_par_type_quand_non_vide(patch_output_dir):
    state = build_state(eligible=True)
    state.resultat.repartition_type_m = {
        "Route à 1 chaussée": 120.5,
        "Chemin": 30.0,
    }

    chemin = pdf_report.generer_rapport_pdf(state)
    texte = _extract_text(chemin)

    assert "Distance routière par type de voie" in texte
    assert "Route à 1 chaussée" in texte
    assert "Chemin" in texte
    assert "120.5 m" in texte
    assert "30.0 m" in texte


def test_pdf_affiche_le_detail_itineraire_et_dernier_troncon(patch_output_dir):
    state = build_state(eligible=True)
    state.resultat.distance_itineraire_m = 150.0
    state.resultat.distance_dernier_troncon_m = 5.0
    state.resultat.distance_routiere_m = 155.0

    chemin = pdf_report.generer_rapport_pdf(state)
    texte = _extract_text(chemin)

    # Le libellé long "Distance routière totale (jusqu'au réseau BT)" est renvoyé sur
    # deux lignes par pdfplumber (largeur de colonne) : on ne vérifie que le début,
    # déjà distinctif et déjà couvert pour la valeur par
    # test_pdf_affiche_les_distances_arrondies.
    assert "Distance à pied jusqu'à la voirie" in texte
    assert "Dernier tronçon (voirie -> réseau BT)" in texte
    assert "Distance routière totale" in texte
    assert "150.0 m" in texte
    assert "5.0 m" in texte
    assert "155.0 m" in texte


def test_pdf_affiche_le_premier_troncon(patch_output_dir):
    state = build_state(eligible=True)
    state.resultat.distance_premier_troncon_m = 5.0
    state.resultat.distance_itineraire_m = 150.0
    state.resultat.distance_dernier_troncon_m = 5.0
    state.resultat.distance_routiere_m = 160.0

    chemin = pdf_report.generer_rapport_pdf(state)
    texte = _extract_text(chemin)

    # Comme pour "Distance routière totale (jusqu'au réseau BT)", ce libellé long est
    # renvoyé sur deux lignes par pdfplumber (largeur de colonne) : on ne vérifie que
    # le début, déjà distinctif.
    assert "Distance du point d'analyse à la route" in texte
    assert "5.0 m" in texte
    assert "160.0 m" in texte


def test_pdf_omet_la_table_repartition_par_type_quand_vide(patch_output_dir):
    state = build_state(eligible=True)
    assert state.resultat.repartition_type_m == {}

    chemin = pdf_report.generer_rapport_pdf(state)
    texte = _extract_text(chemin)

    assert "Distance routière par type de voie" not in texte
