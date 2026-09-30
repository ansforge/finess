"""Pipeline siretisation : établissements FINESS+ ↔ établissements SIRENE."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.scoring import (
    calc_score_nom, calc_score_adresse, calc_score_global, score_textuel,
)
from src.scoring_vectorise import ConfigMatching

# Priorité des noms côté SIRENE, avec la dénomination de l'UL en repli
COLS_NOM_ETAB = [
    "enseigne1_norm_etab",
    "enseigne2_norm_etab",
    "enseigne3_norm_etab",
    "denomination_usuelle_norm_etab",
]
COL_NOM_ETAB_FALLBACK = "denomination_norm_etab"

CONFIG_ST = ConfigMatching(
    col_id="NB_EgeId",
    col_nom="raisonsociale_norm_ege",
    col_commune="cdcommune_norm_ege",
    col_num_voie="nmvoie_norm_ege",
    col_voie="libelle_voie_complet_ege",
    col_bloc="dept_ege",
    col_identifiant="siret_norm_ege",
    col_ape="ape_referentiel",
    col_annee="annee_referentiel",
    cols_noms_droite=COLS_NOM_ETAB,
    col_nom_fallback_droite=COL_NOM_ETAB_FALLBACK,
    col_commune_droite="code_commune_norm_etab",
    col_num_voie_droite="numero_voie_norm_etab",
    col_voie_droite="libelle_voie_complet_etab",
    col_bloc_droite="dept_etab",
    col_identifiant_droite="siret",
    col_ape_droite="activitePrincipaleEtablissement",
    col_annee_droite="annee_creation_etab",
)

COLS_ETAB_EXPORT = [
    "siret", "siren", "denominationUniteLegale",
    "enseigne1Etablissement", "denominationUsuelleEtablissement",
    "adresse_complete_etab", "codeCommuneEtablissement",
    "categorieJuridiqueUniteLegale", "activitePrincipaleEtablissement",
    "dateCreationEtablissement", "etablissementSiege",
]


def choisir_nom_etab(row_etab: pd.Series, nom_ege_norm: str) -> str:
    """Meilleure enseigne ou dénomination usuelle, à défaut la dénomination UL."""
    candidats = [str(row_etab.get(c, "") or "").strip() for c in COLS_NOM_ETAB]
    candidats = [c for c in candidats if c]
    if not candidats:
        return str(row_etab.get(COL_NOM_ETAB_FALLBACK, "") or "").strip()
    if len(candidats) == 1:
        return candidats[0]
    return max(candidats, key=lambda c: score_textuel(nom_ege_norm, c))


def scorer_paire_ege_etab(row_ege: pd.Series, row_etab: pd.Series) -> dict:
    nom_ege = str(row_ege.get("raisonsociale_norm_ege", ""))
    nom_etab = choisir_nom_etab(row_etab, nom_ege)

    s_nom = calc_score_nom(nom_ege, nom_etab)
    s_adr = calc_score_adresse(
        str(row_ege.get("cdcommune_norm_ege", "")), str(row_etab.get("code_commune_norm_etab", "")),
        str(row_ege.get("nmvoie_norm_ege", "")), str(row_etab.get("numero_voie_norm_etab", "")),
        str(row_ege.get("libelle_voie_complet_ege", "")), str(row_etab.get("libelle_voie_complet_etab", "")),
    )
    s_glb = calc_score_global(s_nom, s_adr)
    return {
        "score_nom": round(s_nom, 2),
        "score_adresse": round(s_adr, 2),
        "score_global": round(s_glb, 2),
        "nom_etab_retenu": nom_etab,
    }


# ─── Phase 1 — SIRET exact ───────────────────────────────────────────────────

def matching_direct_siret(df_ege: pd.DataFrame, df_etab: pd.DataFrame) -> pd.DataFrame:
    """Jointure exacte sur le SIRET, puis scoring des paires obtenues."""
    from tqdm.auto import tqdm
    from src.matching import classifier_resultat

    df_ege = df_ege.copy()
    df_ege["siret_norm_ege"] = df_ege["siret_norm_ege"].fillna("").astype(str)

    etab = df_etab.drop_duplicates(subset=["siret"], keep="first").copy()
    etab["siret"] = etab["siret"].astype(str)

    fusion = df_ege.merge(etab, how="left", left_on="siret_norm_ege", right_on="siret",
                          suffixes=("", "_etab"))

    sans_siret = fusion["siret_norm_ege"] == ""
    inconnu = (~sans_siret) & fusion["siret"].isna()
    apparie = (~sans_siret) & fusion["siret"].notna()

    print(f"EGE traités      : {len(fusion):,}")
    print(f"   sans SIRET    : {int(sans_siret.sum()):,}")
    print(f"   SIRET inconnu : {int(inconnu.sum()):,}")
    print(f"   à scorer      : {int(apparie.sum()):,}")

    for col in ("score_nom", "score_adresse", "score_global"):
        fusion[col] = np.nan
    fusion["nom_etab_retenu"] = None
    fusion["statut"] = np.where(sans_siret, "SANS_SIRET",
                                np.where(inconnu, "SIRET_INCONNU", None))
    fusion["siret_etab"] = np.where(sans_siret, None, fusion["siret_norm_ege"])

    indices = fusion.index[apparie]
    resultats = []
    for idx in tqdm(indices, desc="Phase 1 siretisation", total=len(indices)):
        resultats.append(scorer_paire_ege_etab(fusion.loc[idx], fusion.loc[idx]))

    if resultats:
        scores = pd.DataFrame(resultats, index=indices)
        for col in scores.columns:
            fusion.loc[indices, col] = scores[col]
        fusion.loc[indices, "statut"] = [
            classifier_resultat(r["score_global"], r["score_nom"], r["score_adresse"])
            for r in resultats
        ]
    return fusion


def construire_perimetre(df_ege: pd.DataFrame, ids_valides: set) -> pd.DataFrame:
    """Établissements non validés en phase 1, à traiter en phases 2 et 3."""
    ids_norm = {str(i).strip() for i in ids_valides if str(i).strip()}
    exclu = df_ege["NB_EgeId"].astype(str).str.strip().isin(ids_norm)
    perimetre = df_ege[~exclu].reset_index(drop=True)
    print(f"EGE totaux   : {len(df_ege):,}")
    print(f"EGE à traiter: {len(perimetre):,}  (exclus, validés en P1 : {int(exclu.sum()):,})")
    return perimetre
