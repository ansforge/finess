"""Affichage stylé des tableaux et synthèses dans Jupyter."""
from typing import Optional

import pandas as pd
from IPython.display import HTML, display


def afficher_tableau(
    df: pd.DataFrame,
    titre: str,
    max_lignes: int = 5,
    colonnes: Optional[list] = None,
):
    """Tableau stylé avec en-tête bleu marine."""
    if colonnes is not None:
        cols = [c for c in colonnes if c in df.columns]
        df = df[cols]
    df = df.head(max_lignes)

    style = (
        df.style
        .set_caption(titre)
        .set_table_styles([
            {"selector": "caption",
             "props": "caption-side: top; font-weight: bold; "
                      "font-size: 13px; padding: 8px; color: #1F4E79;"},
            {"selector": "th",
             "props": "background-color: #1F4E79; color: white; "
                      "font-family: Arial; font-size: 10pt; "
                      "padding: 6px; text-align: center;"},
            {"selector": "td",
             "props": "font-family: Arial; font-size: 10pt; padding: 4px 8px;"},
            {"selector": "tr:nth-child(even)",
             "props": "background-color: #F2F6FC;"},
        ])
        .hide(axis="index")
    )
    display(HTML(style.to_html()))


def afficher_synthese(compteurs: dict, titre: str):
    """Synthèse colorée des compteurs par statut."""
    couleurs = {
        "Valide_fort":     "#C6EFCE",
        "Valide":          "#D9F0E3",
        "Valide_fort_P1":  "#C6EFCE",
        "Valide_P1":       "#D9F0E3",
        "Valide_fort_P2":  "#E2F0D9",
        "Valide_P2":       "#EAF1DC",
        "Valide_fort_P3":  "#F0F4E0",
        "Valide_P3":       "#F4F7E5",
        "Douteux":         "#FFEB9C",
        "Rejeté":          "#FFC7CE",
        "Sans_SIRET":      "#E2E2E2",
        "SIRET_inconnu":   "#ECECEC",
        "Sans_SIREN":      "#E2E2E2",
        "SIREN_inconnu":   "#ECECEC",
        "Sans_candidat":   "#ECECEC",
        "TOTAL":           "#D9E1F2",
    }
    total = sum(compteurs.values())
    rows = []
    for label, n in compteurs.items():
        pct = round(n / total * 100, 1) if total else 0.0
        rows.append((label, n, pct))
    rows.append(("TOTAL", total, 100.0))

    html = [f'<table style="border-collapse:collapse;font-family:Arial;font-size:10pt;">']
    html.append(
        f'<caption style="caption-side:top;font-weight:bold;font-size:13px;'
        f'padding:8px;color:#1F4E79;">{titre}</caption>'
    )
    html.append(
        '<tr style="background-color:#1F4E79;color:white;">'
        '<th style="padding:6px 12px;">Statut</th>'
        '<th style="padding:6px 12px;">Nb</th>'
        '<th style="padding:6px 12px;">% du total</th></tr>'
    )
    for label, n, pct in rows:
        bg = couleurs.get(label, "#FFFFFF")
        bold = "font-weight:bold;" if label == "TOTAL" else ""
        html.append(
            f'<tr style="background-color:{bg};{bold}">'
            f'<td style="padding:4px 12px;">{label}</td>'
            f'<td style="padding:4px 12px;text-align:right;">{n:,}</td>'
            f'<td style="padding:4px 12px;text-align:right;">{pct}%</td></tr>'
        )
    html.append("</table>")
    display(HTML("".join(html)))
