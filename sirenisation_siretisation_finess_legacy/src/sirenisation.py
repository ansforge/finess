"""Pipeline sirenisation : matching EJ FINESS ↔ UL SIRENE."""
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ─── Sélection du nom UL ─────────────────────────────────────────────────────

def choisir_nom_ul(row_ul: pd.Series, nom_ej_norm: str) -> str:
    """
    Pour les UL : priorité dénomination, fallback sigle.
    Si les deux sont renseignés, on garde celui qui matche le mieux le nom EJ.
    """
    from src.scoring import score_textuel

    denom = str(row_ul.get("denomination_norm_ul", "") or "").strip()
    sigle = str(row_ul.get("sigle_norm_ul",        "") or "").strip()

    if denom and sigle:
        return denom if score_textuel(nom_ej_norm, denom) >= score_textuel(nom_ej_norm, sigle) else sigle
    return denom or sigle


# ─── Scoring d'une paire EJ/UL ───────────────────────────────────────────────

def scorer_paire_ej_ul(row_ej: pd.Series, row_ul: pd.Series) -> dict:
    from src.scoring import (
        calc_score_nom, calc_score_adresse, calc_score_global,
    )

    nom_ej = str(row_ej.get("raisonsociale_norm_ej", ""))
    nom_ul = choisir_nom_ul(row_ul, nom_ej)

    s_nom = calc_score_nom(nom_ej, nom_ul)
    s_adr = calc_score_adresse(
        str(row_ej.get("cdcommune_norm_ej", "")),
        str(row_ul.get("code_commune_norm_ul", "")),
        str(row_ej.get("nmvoie_norm_ej", "")),
        str(row_ul.get("numero_voie_norm_ul", "")),
        str(row_ej.get("libelle_voie_complet_ej", "")),
        str(row_ul.get("libelle_voie_complet_ul", "")),
    )
    s_glb = calc_score_global(s_nom, s_adr)

    return {
        "score_nom":     round(s_nom, 2),
        "score_adresse": round(s_adr, 2),
        "score_global":  round(s_glb, 2),
        "nom_ul_retenu": nom_ul,
    }


# ─── Phase 1 — matching SIREN exact ──────────────────────────────────────────

def matching_direct_siren(
    df_ej_clean: pd.DataFrame,
    df_ul_clean: pd.DataFrame,
    desc: str = "Matching direct SIREN",
    show_progress: bool = True,
) -> pd.DataFrame:
    """
    Phase 1 sirenisation : pour chaque EJ, lookup SIREN exact dans la base UL.
    """
    from tqdm.auto import tqdm
    from src.matching import classifier_resultat

    ul_idx = df_ul_clean.set_index("siren")
    resultats = []

    rows = df_ej_clean.iterrows()
    if show_progress:
        rows = tqdm(rows, total=len(df_ej_clean), desc=desc)

    for _, row_ej in rows:
        siren_ej = str(row_ej.get("nmsiren_stru", "") or "").strip().replace(" ", "")
        base = row_ej.to_dict()

        if not siren_ej or siren_ej in ("nan", "None"):
            resultats.append({**base,
                "siren_ul": None, "score_nom": None,
                "score_adresse": None, "score_global": None,
                "nom_ul_retenu": None, "statut": "SANS_SIREN"})
            continue

        if siren_ej not in ul_idx.index:
            resultats.append({**base,
                "siren_ul": siren_ej, "score_nom": None,
                "score_adresse": None, "score_global": None,
                "nom_ul_retenu": None, "statut": "SIREN_INCONNU"})
            continue

        row_ul = ul_idx.loc[siren_ej]
        if isinstance(row_ul, pd.DataFrame):
            row_ul = row_ul.iloc[0]
        scores = scorer_paire_ej_ul(row_ej, row_ul)
        statut = classifier_resultat(
            scores["score_global"], scores["score_nom"], scores["score_adresse"])
        resultats.append({**base, "siren_ul": siren_ej, **scores, "statut": statut})

    return pd.DataFrame(resultats)


# ─── Construction du périmètre A/B/C sur les non-validés P1 ──────────────────

def construire_perimetre_abc(
    df_ej: pd.DataFrame,
    df_eg: pd.DataFrame,
    ids_valides: set,
) -> pd.DataFrame:
    """
    Construit le périmètre des EJ à traiter en Phase 2/3.

    Sous-ensembles :
        A : EJ rattachés à au moins une EG (via nmfinessej_stru côté EG)
        B : EJ non rattachés à une EG mais avec nmsiren_stru renseigné
        C : EJ non rattachés à une EG ET sans nmsiren_stru

    Étapes :
        1. base_complete = A ∪ B ∪ C (toutes les lignes EJ)
        2. Retirer les EJ dont idstructure_stru ∈ ids_valides
           (on exclut sur l'identifiant FINESS unique, pas sur le SIREN,
           pour ne pas écarter les "EJ jumeaux" qui partagent un SIREN
           validé mais ne sont pas eux-mêmes validés)
    """
    df_ej = df_ej.copy()
    df_ej["nmsiren_stru"] = (
        df_ej["nmsiren_stru"].fillna("").astype(str)
        .str.replace(r"\s", "", regex=True).str.strip()
    )

    ej_avec_eg = set(
        df_eg["nmfinessej_stru"].dropna().astype(str).str.strip().unique()
    )
    ej_avec_eg.discard("")

    df_ej["_id_str"] = df_ej["idstructure_stru"].astype(str).str.strip()

    mask_a = df_ej["_id_str"].isin(ej_avec_eg)
    mask_b = (~mask_a) & (df_ej["nmsiren_stru"] != "")
    mask_c = (~mask_a) & (df_ej["nmsiren_stru"] == "")

    df_ej.loc[mask_a, "sous_ensemble"] = "A"
    df_ej.loc[mask_b, "sous_ensemble"] = "B"
    df_ej.loc[mask_c, "sous_ensemble"] = "C"

    base = df_ej.copy()

    ids_valides_norm = {str(s).strip() for s in ids_valides if s}
    mask_exclu = base["_id_str"].isin(ids_valides_norm)
    return base[~mask_exclu].drop(columns=["_id_str"]).copy().reset_index(drop=True)


# ─── Phase 3 : matching approfondi (APE + date) ──────────────────────────────

def _extraire_annee(date_str) -> Optional[int]:
    if date_str is None or (isinstance(date_str, float) and pd.isna(date_str)):
        return None
    s = str(date_str).strip()
    if len(s) < 4:
        return None
    try:
        return int(s[:4])
    except ValueError:
        return None


def normaliser_ape(code) -> str:
    if code is None or (isinstance(code, float) and pd.isna(code)):
        return ""
    return str(code).strip().upper().replace(".", "").replace(" ", "")


def score_ape(ape_finess: str, ape_sirene: str) -> Optional[float]:
    """
    100 : codes identiques
     70 : même classe (4 premiers car.)
     40 : même groupe (3 premiers car.)
     20 : même division (2 premiers car.)
      0 : pas de cohérence
   None : un APE manquant (cas neutre)
    """
    a = normaliser_ape(ape_finess)
    b = normaliser_ape(ape_sirene)
    if not a or not b:
        return None
    if a == b:        return 100.0
    if a[:4] == b[:4]: return 70.0
    if a[:3] == b[:3]: return 40.0
    if a[:2] == b[:2]: return 20.0
    return 0.0


def score_date(annee_finess: Optional[int], annee_sirene: Optional[int]) -> Optional[float]:
    """
    100 : écart ≤ 1 an   |   80 : ≤ 3   |   60 : ≤ 5
     40 : ≤ 10           |   20 : ≤ 20  |    0 : > 20
    None : une année manquante
    """
    if annee_finess is None or annee_sirene is None:
        return None
    ecart = abs(annee_finess - annee_sirene)
    if ecart <= 1:  return 100.0
    if ecart <= 3:  return 80.0
    if ecart <= 5:  return 60.0
    if ecart <= 10: return 40.0
    if ecart <= 20: return 20.0
    return 0.0


def scorer_paire_approfondi(row_ej: pd.Series, row_ul: pd.Series) -> dict:
    """
    Scoring Phase 3 : reprend le scoring textuel + adresse, ajoute APE et date.

    Pondération adaptative :
        - APE et date dispos : 0.70 × global + 0.20 × ape + 0.10 × date
        - APE seul           : 0.80 × global + 0.20 × ape
        - date seule         : 0.80 × global + 0.20 × date
        - aucun              : score_global standard
    """
    base = scorer_paire_ej_ul(row_ej, row_ul)

    s_ape  = score_ape(row_ej.get("cdape_stru"), row_ul.get("activitePrincipaleUniteLegale"))
    annee_f = _extraire_annee(row_ej.get("dtouvertstruct_stru"))
    annee_s = _extraire_annee(row_ul.get("dateCreationUniteLegale"))
    s_date = score_date(annee_f, annee_s)

    if s_ape is not None and s_date is not None:
        s_glb_app = 0.70 * base["score_global"] + 0.20 * s_ape + 0.10 * s_date
    elif s_ape is not None:
        s_glb_app = 0.80 * base["score_global"] + 0.20 * s_ape
    elif s_date is not None:
        s_glb_app = 0.80 * base["score_global"] + 0.20 * s_date
    else:
        s_glb_app = base["score_global"]

    return {
        **base,
        "score_ape":               round(s_ape,  2) if s_ape  is not None else None,
        "score_date":              round(s_date, 2) if s_date is not None else None,
        "annee_creation_ej":       annee_f,
        "annee_creation_ul":       annee_s,
        "ape_ej":                  normaliser_ape(row_ej.get("cdape_stru")),
        "ape_ul":                  normaliser_ape(row_ul.get("activitePrincipaleUniteLegale")),
        "score_global_approfondi": round(s_glb_app, 2),
    }
