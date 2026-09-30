"""Pipeline sirenisation : personnes morales FINESS+ ↔ unités légales SIRENE."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.scoring import (
    calc_score_nom, calc_score_adresse, calc_score_global, score_textuel,
)
from src.scoring_vectorise import ConfigMatching

CONFIG_SN = ConfigMatching(
    col_id="NB_PmSmsseId",
    col_nom="raisonsociale_norm_pm",
    col_commune="cdcommune_norm_pm",
    col_num_voie="nmvoie_norm_pm",
    col_voie="libelle_voie_complet_pm",
    col_bloc="dept_pm",
    col_identifiant="siren_norm_pm",
    col_ape="ape_referentiel",
    col_annee="annee_referentiel",
    cols_noms_droite=["denomination_norm_ul", "sigle_norm_ul"],
    col_nom_fallback_droite=None,
    col_commune_droite="code_commune_norm_ul",
    col_num_voie_droite="numero_voie_norm_ul",
    col_voie_droite="libelle_voie_complet_ul",
    col_bloc_droite="dept_ul",
    col_identifiant_droite="siren",
    col_ape_droite="activitePrincipaleUniteLegale",
    col_annee_droite="annee_creation_ul",
)

COLS_UL_EXPORT = [
    "siren", "denominationUniteLegale", "sigleUniteLegale",
    "adresse_siege_complete_ul", "codeCommuneEtablissement",
    "categorieJuridiqueUniteLegale", "activitePrincipaleUniteLegale",
    "dateCreationUniteLegale",
]


def choisir_nom_ul(row_ul: pd.Series, nom_pm_norm: str) -> str:
    """Dénomination ou sigle, celui qui ressemble le plus au nom FINESS."""
    denom = str(row_ul.get("denomination_norm_ul", "") or "").strip()
    sigle = str(row_ul.get("sigle_norm_ul", "") or "").strip()
    if denom and sigle:
        return denom if score_textuel(nom_pm_norm, denom) >= score_textuel(nom_pm_norm, sigle) else sigle
    return denom or sigle


def scorer_paire_pm_ul(row_pm: pd.Series, row_ul: pd.Series) -> dict:
    """Scoring d'une paire, pour la phase 1 où le candidat est unique."""
    nom_pm = str(row_pm.get("raisonsociale_norm_pm", ""))
    nom_ul = choisir_nom_ul(row_ul, nom_pm)

    s_nom = calc_score_nom(nom_pm, nom_ul)
    s_adr = calc_score_adresse(
        str(row_pm.get("cdcommune_norm_pm", "")), str(row_ul.get("code_commune_norm_ul", "")),
        str(row_pm.get("nmvoie_norm_pm", "")), str(row_ul.get("numero_voie_norm_ul", "")),
        str(row_pm.get("libelle_voie_complet_pm", "")), str(row_ul.get("libelle_voie_complet_ul", "")),
    )
    s_glb = calc_score_global(s_nom, s_adr)
    return {
        "score_nom": round(s_nom, 2),
        "score_adresse": round(s_adr, 2),
        "score_global": round(s_glb, 2),
        "nom_ul_retenu": nom_ul,
    }


# ─── Phase 1 — SIREN exact, vectorisée ───────────────────────────────────────

def matching_direct_siren(df_pm: pd.DataFrame, df_ul: pd.DataFrame) -> pd.DataFrame:
    """Jointure exacte sur le SIREN, puis scoring des paires obtenues.

    Statuts : VALIDE_FORT, VALIDE, DOUTEUX, REJETE, plus SANS_SIREN quand le
    SIREN n'est pas renseigné et SIREN_INCONNU quand il est absent de SIRENE.
    """
    from tqdm.auto import tqdm
    from src.matching import classifier_resultat

    df_pm = df_pm.copy()
    df_pm["siren_norm_pm"] = df_pm["siren_norm_pm"].fillna("").astype(str)

    ul = df_ul.drop_duplicates(subset=["siren"], keep="first").copy()
    ul["siren"] = ul["siren"].astype(str)

    fusion = df_pm.merge(ul, how="left", left_on="siren_norm_pm", right_on="siren",
                         suffixes=("", "_ul"))

    sans_siren = fusion["siren_norm_pm"] == ""
    inconnu = (~sans_siren) & fusion["siren"].isna()
    apparie = (~sans_siren) & fusion["siren"].notna()

    print(f"PM traitées      : {len(fusion):,}")
    print(f"   sans SIREN    : {int(sans_siren.sum()):,}")
    print(f"   SIREN inconnu : {int(inconnu.sum()):,}")
    print(f"   à scorer      : {int(apparie.sum()):,}")

    for col in ("score_nom", "score_adresse", "score_global"):
        fusion[col] = np.nan
    fusion["nom_ul_retenu"] = None
    fusion["statut"] = np.where(sans_siren, "SANS_SIREN",
                                np.where(inconnu, "SIREN_INCONNU", None))
    fusion["siren_ul"] = np.where(sans_siren, None, fusion["siren_norm_pm"])

    indices = fusion.index[apparie]
    resultats = []
    for idx in tqdm(indices, desc="Phase 1 sirenisation", total=len(indices)):
        resultats.append(scorer_paire_pm_ul(fusion.loc[idx], fusion.loc[idx]))

    if resultats:
        scores = pd.DataFrame(resultats, index=indices)
        for col in scores.columns:
            fusion.loc[indices, col] = scores[col]
        fusion.loc[indices, "statut"] = [
            classifier_resultat(r["score_global"], r["score_nom"], r["score_adresse"])
            for r in resultats
        ]
    return fusion


# ─── Périmètre A/B/C ─────────────────────────────────────────────────────────

def construire_perimetre_abc(df_pm: pd.DataFrame, df_ege: pd.DataFrame,
                             ids_valides: set) -> pd.DataFrame:
    """Périmètre des PM à traiter en phases 2 et 3.

    A : rattachées à au moins un établissement.
    B : sans établissement mais avec un SIREN renseigné.
    C : sans établissement et sans SIREN.

    L'exclusion porte sur NB_PmSmsseId et non sur le SIREN : deux PM jumelles
    partageant un SIREN validé ne sont pas écartées si elles-mêmes ne l'ont pas
    été.
    """
    df_pm = df_pm.copy()
    pm_avec_ege = set(
        pd.to_numeric(df_ege["NB_PmSmsseId"], errors="coerce").dropna().astype("int64")
    )
    cle = pd.to_numeric(df_pm["NB_PmSmsseId"], errors="coerce")

    mask_a = cle.isin(pm_avec_ege)
    a_siren = df_pm["siren_norm_pm"].fillna("").astype(str) != ""
    df_pm["sous_ensemble"] = np.where(mask_a, "A", np.where(a_siren, "B", "C"))

    ids_norm = {str(i).strip() for i in ids_valides if str(i).strip()}
    exclu = df_pm["NB_PmSmsseId"].astype(str).str.strip().isin(ids_norm)

    perimetre = df_pm[~exclu].reset_index(drop=True)
    print(f"PM totales   : {len(df_pm):,}")
    print(f"PM à traiter : {len(perimetre):,}  (exclues, validées en P1 : {int(exclu.sum()):,})")
    print(f"   A (avec établissement) : {(perimetre['sous_ensemble'] == 'A').sum():,}")
    print(f"   B (sans EG, avec SIREN): {(perimetre['sous_ensemble'] == 'B').sum():,}")
    print(f"   C (sans EG, sans SIREN): {(perimetre['sous_ensemble'] == 'C').sum():,}")
    return perimetre
