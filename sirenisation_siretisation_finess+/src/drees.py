"""Lecture des données de rapprochement et de revue produites par la DREES.

Deux sources complémentaires. Le fichier de propositions couvre toute la
population et porte les variables du modèle. L'échantillon de revue manuelle
apporte la vérité terrain et les poids de sondage sur les structures examinées.

Le tirage étant stratifié, chaque structure examinée représente un nombre variable
de structures de la population. Toutes les mesures sont donc pondérées : un
chiffre brut ne décrirait que l'échantillon.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Cohérence SIREN calculée avec le SIREN corrigé par la revue manuelle. C'est la
# variable du modèle publié, mais elle n'existe que sur les structures examinées.
COL_COHERENCE_REVUE = "coherence_siren_du_siret_avec_siren_ej_corrige"

# Cohérence issue de notre propre chaîne, disponible sur toute la population.
COL_COHERENCE_ANS = "coherence_EGE_ANS"

SOURCES_ANS = ("ANS", "both")


def charger_propositions(chemin) -> pd.DataFrame:
    """Candidats proposés par les deux chaînes, sur toute la population."""
    d = pd.read_parquet(chemin)
    print(f"   {len(d):,} candidats, {d['EGE'].nunique():,} structures")
    print(f"   origine : {d['proposal_source'].value_counts().to_dict()}")
    return d


def propositions_ans(propositions: pd.DataFrame, cle: str = "EGE") -> pd.DataFrame:
    """Proposition la mieux classée de notre chaîne, une par structure."""
    ans = (propositions[propositions["proposal_source"].isin(SOURCES_ANS)]
           .sort_values([cle, "candidate_rank"])
           .drop_duplicates(cle, keep="first"))
    print(f"   {len(ans):,} structures avec une proposition de notre chaine")
    return ans


def charger_echantillon(chemin) -> pd.DataFrame:
    """Échantillon de revue : vérité terrain et poids calibrés."""
    ech = pd.read_excel(chemin, dtype=str)
    for col in ("sampling_weight", "calibrated_weight"):
        if col in ech.columns:
            ech[col] = pd.to_numeric(ech[col], errors="coerce")
    col_retenu = next(c for c in ech.columns if c.startswith("Si"))
    print(f"   {len(ech):,} structures examinees, "
          f"{ech[col_retenu].notna().sum():,} avec un identifiant retenu")
    return ech


def _normaliser(serie: pd.Series) -> pd.Series:
    return serie.fillna("").astype(str).str.replace(r"\s", "", regex=True)


def table_apprentissage(propositions: pd.DataFrame, echantillon: pd.DataFrame,
                        niveau: str = "ege") -> pd.DataFrame:
    """Une ligne par structure examinée : notre proposition, et si elle est juste.

    Les structures à fermer sont écartées. Une structure sans identifiant retenu
    compte comme une proposition incorrecte : la revue n'a validé aucun candidat.
    """
    cle = "EGE" if niveau == "ege" else "EJ"
    col_retenu = "Siret_retenu" if niveau == "ege" else "Siren_retenu"
    col_propose = "siret_proposal" if niveau == "ege" else "siren_proposal"

    ans = propositions_ans(propositions, cle)
    cols = [c for c in (cle, col_retenu, "calibrated_weight", "to_close")
            if c in echantillon.columns]

    table = echantillon[cols].merge(ans, on=cle, how="inner")
    print(f"   {len(table):,} structures examinees avec une proposition")

    if "to_close" in table.columns:
        avant = len(table)
        table = table[table["to_close"] != "True"]
        print(f"   {avant - len(table):,} a fermer ecartees -> {len(table):,} exploitables")

    table["y"] = (_normaliser(table[col_propose])
                  == _normaliser(table[col_retenu])).astype(int)
    table.loc[table[col_retenu].isna(), "y"] = 0

    poids = table["calibrated_weight"]
    print(f"   proposition correcte : {table['y'].sum():,} / {len(table):,} "
          f"({(table['y'] * poids).sum() / poids.sum() * 100:.1f} % pondere)")
    return table.reset_index(drop=True)
