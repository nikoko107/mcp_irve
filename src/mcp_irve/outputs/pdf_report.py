"""Génération du rapport PDF (outil generer_rapport_pdf).

Les trois mises en garde ci-dessous sont un contrat avec le cahier des charges
(section "Points de vigilance à documenter dans le rapport") : toute modification de
ce module doit les préserver telles quelles, un test dédié (tests/outputs/test_pdf_report.py)
vérifie leur présence par extraction du texte du PDF généré.
"""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

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


def _table(
    rows: list[list[str]], label_style: ParagraphStyle, value_style: ParagraphStyle
) -> Table:
    # Chaque cellule est un Paragraph (pas une simple chaîne) pour que le texte se
    # replie correctement dans la largeur de colonne au lieu de déborder sur la
    # colonne voisine (constaté sur "Coordonnées Lambert 93 (EPSG:2154)").
    wrapped_rows = [
        [Paragraph(escape(str(label)), label_style), Paragraph(escape(str(value)), value_style)]
        for label, value in rows
    ]
    table = Table(wrapped_rows, colWidths=[6.5 * cm, 9.5 * cm])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#dddddd")),
            ]
        )
    )
    return table


def generer_rapport_pdf(state: SessionState) -> Path:
    assert state.point_depart is not None
    assert state.resultat is not None
    point = state.point_depart
    resultat = state.resultat

    styles = getSampleStyleSheet()
    h2 = styles["Heading2"]
    body = styles["BodyText"]
    warning_style = ParagraphStyle(
        "Avertissement", parent=body, textColor=colors.HexColor("#7a5b00"), fontSize=9
    )
    statut_color = colors.HexColor("#1a7f37") if resultat.eligible else colors.HexColor("#b3261e")
    statut_style = ParagraphStyle("Statut", parent=h2, textColor=statut_color)
    label_style = ParagraphStyle("Label", parent=body, fontName="Helvetica-Bold", fontSize=9.5)
    value_style = ParagraphStyle("Value", parent=body, fontSize=9.5)

    chemin = new_output_path("rapport", "pdf")
    doc = SimpleDocTemplate(str(chemin), pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm)

    elements = [
        Paragraph("Rapport de raccordement IRVE", styles["Title"]),
        Paragraph("Éligibilité au réseau BT Enedis — distance routière", body),
        Spacer(1, 0.5 * cm),
        Paragraph("ÉLIGIBLE" if resultat.eligible else "NON ÉLIGIBLE", statut_style),
        Spacer(1, 0.3 * cm),
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
        ),
    ]

    if resultat.repartition_type_m:
        elements += [
            Spacer(1, 0.4 * cm),
            Paragraph("Distance routière par type de voie", h2),
            _table(
                [
                    [type_voie, f"{longueur:.1f} m"]
                    for type_voie, longueur in resultat.repartition_type_m.items()
                ],
                label_style,
                value_style,
            ),
        ]

    elements += [
        Spacer(1, 0.5 * cm),
        Paragraph("Limites et fiabilité", h2),
    ]
    for mise_en_garde in MISES_EN_GARDE:
        elements.append(Paragraph(f"• {mise_en_garde}", warning_style))
        elements.append(Spacer(1, 0.15 * cm))

    doc.build(elements)
    return chemin
