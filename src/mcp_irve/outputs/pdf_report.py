"""Génération du rapport PDF (outil generer_rapport_pdf).

Les trois mises en garde ci-dessous sont un contrat avec le cahier des charges
(section "Points de vigilance à documenter dans le rapport") : toute modification de
ce module doit les préserver telles quelles, un test dédié (tests/outputs/test_pdf_report.py)
vérifie leur présence par extraction du texte du PDF généré.

Palette et mise en page pensées pour la lisibilité : statut d'éligibilité et mises en
garde dans des encadrés à fond coloré (pas seulement du texte coloré, plus visible en
lecture rapide), en-têtes de colonnes et zébrage sur les tables à lignes homogènes.
Toutes les couleurs restent des teintes Latin-1/WinAnsi-safe appliquées via `colors`
reportlab — aucun caractère hors de cette plage n'est introduit dans le texte (cf.
piège Helvetica documenté plus bas, ex. `≠` mal rendu).
"""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..config import SETTINGS
from ..state import SessionState
from ._shared import new_output_path

MISES_EN_GARDE = [
    "Les données réseau BT Enedis en open data sont déclaratives, non garanties "
    "exhaustives ni à jour en temps réel.",
    "La distance routière calculée est une approximation de la distance de "
    "raccordement réelle (le tracé de voirie n'est pas le tracé de tranchée/génie civil réel).",
    "Le seuil d'éligibilité de 200 m s'applique à la distance routière, pas à la "
    "distance à vol d'oiseau.",
]

# --- Palette ---
_LARGEUR_TABLE = 16 * cm  # cohérent avec les colWidths historiques (6.5 cm + 9.5 cm)

COULEUR_PRIMAIRE = colors.HexColor("#1f2d3d")  # titres et en-têtes de section
COULEUR_TEXTE_ATTENUE = colors.HexColor("#5a6472")  # sous-titre, texte secondaire
COULEUR_BORDURE = colors.HexColor("#dde1e6")  # filets de table
COULEUR_ENTETE_FOND = colors.HexColor("#eef1f5")  # fond des en-têtes de colonnes
COULEUR_ZEBRE = colors.HexColor("#f7f8fa")  # fond des lignes paires

COULEUR_SUCCES = colors.HexColor("#1a7f37")
COULEUR_SUCCES_FOND = colors.HexColor("#e6f4ea")
COULEUR_DANGER = colors.HexColor("#b3261e")
COULEUR_DANGER_FOND = colors.HexColor("#fdecea")

COULEUR_AVERTISSEMENT_TEXTE = colors.HexColor("#7a5b00")
COULEUR_AVERTISSEMENT_FOND = colors.HexColor("#fff8e6")
COULEUR_AVERTISSEMENT_BORDURE = colors.HexColor("#f0c93b")


def _table(
    rows: list[list[str]],
    label_style: ParagraphStyle,
    value_style: ParagraphStyle,
    header_style: ParagraphStyle,
    *,
    headers: tuple[str, str] | None = None,
    zebre: bool = False,
) -> Table:
    # Chaque cellule est un Paragraph (pas une simple chaîne) pour que le texte se
    # replie correctement dans la largeur de colonne au lieu de déborder sur la
    # colonne voisine (constaté sur "Coordonnées Lambert 93 (EPSG:2154)").
    corps = [
        [Paragraph(escape(str(label)), label_style), Paragraph(escape(str(value)), value_style)]
        for label, value in rows
    ]

    style_commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, COULEUR_BORDURE),
    ]

    donnees = corps
    decalage = 0
    if headers is not None:
        entete = [
            Paragraph(escape(headers[0]), header_style),
            Paragraph(escape(headers[1]), header_style),
        ]
        donnees = [entete] + corps
        decalage = 1
        style_commands += [
            ("BACKGROUND", (0, 0), (-1, 0), COULEUR_ENTETE_FOND),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, COULEUR_BORDURE),
        ]

    if zebre:
        for i in range(1, len(corps), 2):
            ligne = i + decalage
            style_commands.append(("BACKGROUND", (0, ligne), (-1, ligne), COULEUR_ZEBRE))

    table = Table(donnees, colWidths=[6.5 * cm, 9.5 * cm])
    table.setStyle(TableStyle(style_commands))
    return table


def _part_pourcentage(longueur: float, total: float) -> str:
    return f" ({100 * longueur / total:.0f} %)" if total else ""


def _encadre(flowables: list, fond, bordure) -> Table:
    """Encadré à fond coloré (statut d'éligibilité, mises en garde) : un fond de
    couleur porte mieux l'attention en lecture rapide qu'un simple texte coloré."""
    encadre = Table([[flowables]], colWidths=[_LARGEUR_TABLE])
    encadre.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), fond),
                ("LINEBEFORE", (0, 0), (0, -1), 3, bordure),
                ("BOX", (0, 0), (-1, -1), 0.5, bordure),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return encadre


def generer_rapport_pdf(state: SessionState) -> Path:
    assert state.point_depart is not None
    assert state.resultat is not None
    point = state.point_depart
    resultat = state.resultat

    styles = getSampleStyleSheet()
    body = styles["BodyText"]
    title_style = ParagraphStyle("TitreColore", parent=styles["Title"], textColor=COULEUR_PRIMAIRE)
    sous_titre_style = ParagraphStyle(
        "SousTitre", parent=body, textColor=COULEUR_TEXTE_ATTENUE, fontSize=10.5
    )
    h2 = ParagraphStyle(
        "TitreSection", parent=styles["Heading2"], textColor=COULEUR_PRIMAIRE, spaceAfter=4
    )
    warning_style = ParagraphStyle(
        "Avertissement", parent=body, textColor=COULEUR_AVERTISSEMENT_TEXTE, fontSize=9
    )
    label_style = ParagraphStyle("Label", parent=body, fontName="Helvetica-Bold", fontSize=9.5)
    value_style = ParagraphStyle("Value", parent=body, fontSize=9.5)
    header_style = ParagraphStyle(
        "Entete", parent=label_style, textColor=COULEUR_PRIMAIRE, fontSize=9
    )

    if resultat.eligible:
        statut_fond, statut_couleur = COULEUR_SUCCES_FOND, COULEUR_SUCCES
        statut_texte = "ÉLIGIBLE"
        statut_detail = (
            f"Distance routière de {resultat.distance_routiere_m:.1f} m, inférieure ou égale "
            f"au seuil d'éligibilité de {SETTINGS.seuil_eligibilite_m:.0f} m."
        )
    else:
        statut_fond, statut_couleur = COULEUR_DANGER_FOND, COULEUR_DANGER
        statut_texte = "NON ÉLIGIBLE"
        statut_detail = (
            f"Distance routière de {resultat.distance_routiere_m:.1f} m, supérieure "
            f"au seuil d'éligibilité de {SETTINGS.seuil_eligibilite_m:.0f} m."
        )
    statut_style = ParagraphStyle("Statut", parent=h2, textColor=statut_couleur, spaceAfter=2)
    statut_detail_style = ParagraphStyle(
        "StatutDetail", parent=body, textColor=statut_couleur, fontSize=9.5
    )

    chemin = new_output_path("rapport", "pdf")
    doc = SimpleDocTemplate(str(chemin), pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm)

    elements = [
        Paragraph("Rapport de raccordement IRVE", title_style),
        Paragraph("Éligibilité au réseau BT Enedis — distance routière", sous_titre_style),
        HRFlowable(
            width="100%", thickness=0.75, color=COULEUR_BORDURE, spaceBefore=6, spaceAfter=10
        ),
        _encadre(
            [Paragraph(statut_texte, statut_style), Paragraph(statut_detail, statut_detail_style)],
            statut_fond,
            statut_couleur,
        ),
        Spacer(1, 0.4 * cm),
        Paragraph("Point de départ", h2),
        _table(
            [
                ["Adresse", state.adresse_normalisee or ""],
                ["Coordonnées WGS84", f"{point.lat:.6f}, {point.lon:.6f}"],
                [
                    "Coordonnées Lambert 93 (EPSG:2154)",
                    f"{point.x_l93:.2f}, {point.y_l93:.2f}",
                ],
            ],
            label_style,
            value_style,
            header_style,
            zebre=True,
        ),
        Spacer(1, 0.4 * cm),
        Paragraph("Tronçon de raccordement retenu", h2),
        _table(
            [
                ["Identifiant", resultat.troncon_id],
                ["Type", resultat.type],
                ["Longueur du segment candidat", f"{resultat.candidat.length_m:.1f} m"],
                ["Distance à vol d'oiseau", f"{resultat.distance_vol_oiseau_m:.1f} m"],
                ["Distance routière", f"{resultat.distance_routiere_m:.1f} m"],
                ["Seuil d'éligibilité", f"{SETTINGS.seuil_eligibilite_m:.0f} m"],
                [
                    "Point de raccordement (WGS84)",
                    f"{resultat.point_raccordement.lat:.6f}, {resultat.point_raccordement.lon:.6f}",
                ],
            ],
            label_style,
            value_style,
            header_style,
            zebre=True,
        ),
    ]

    if resultat.repartition_type_m:
        total_repartition = sum(resultat.repartition_type_m.values())
        elements += [
            Spacer(1, 0.4 * cm),
            Paragraph("Distance routière par type de voie", h2),
            _table(
                [
                    [
                        type_voie,
                        f"{longueur:.1f} m" + _part_pourcentage(longueur, total_repartition),
                    ]
                    for type_voie, longueur in resultat.repartition_type_m.items()
                ],
                label_style,
                value_style,
                header_style,
                headers=("Type de voie", "Longueur (part de la distance routière)"),
            ),
        ]

    elements += [
        Spacer(1, 0.5 * cm),
        Paragraph("Limites et fiabilité", h2),
        _encadre(
            [Paragraph(f"• {m}", warning_style) for m in MISES_EN_GARDE],
            COULEUR_AVERTISSEMENT_FOND,
            COULEUR_AVERTISSEMENT_BORDURE,
        ),
    ]

    doc.build(elements)
    return chemin
