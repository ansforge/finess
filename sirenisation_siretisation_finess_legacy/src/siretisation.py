"""Pipeline siretisation : matching EG FINESS ↔ établissement SIRENE."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ─── Sélection du nom d'établissement (règle métier siretisation) ────────────

COLS_NOM_ETAB_ETAB = [
    "enseigne1_norm_etab",
    "enseigne2_norm_etab",
    "enseigne3_norm_etab",
    "denomination_usuelle_norm_etab",
]
COL_NOM_ETAB_FALLBACK = "denomination_norm_etab"


def choisir_nom_etab(row_etab: pd.Series, nom_eg_norm: str) -> str:
    """
    Priorité : enseigne1/2/3, dénomination usuelle. Si plusieurs renseignées,
    on retient la plus proche du nom EG. Fallback : dénomination UL.
    """
    from src.scoring import score_textuel

    candidats = [str(row_etab.get(c, "") or "").strip() for c in COLS_NOM_ETAB_ETAB]
    candidats = [c for c in candidats if c]

    if not candidats:
        return str(row_etab.get(COL_NOM_ETAB_FALLBACK, "") or "").strip()
    if len(candidats) == 1:
        return candidats[0]
    return max(candidats, key=lambda c: score_textuel(nom_eg_norm, c))


# ─── Scoring d'une paire EG/établissement ────────────────────────────────────

def scorer_paire_eg_etab(row_eg: pd.Series, row_etab: pd.Series) -> dict:
    from src.scoring import (
        calc_score_nom, calc_score_adresse, calc_score_global,
    )

    nom_eg   = str(row_eg.get("raisonsociale_norm_eg", ""))
    nom_etab = choisir_nom_etab(row_etab, nom_eg)

    s_nom = calc_score_nom(nom_eg, nom_etab)
    s_adr = calc_score_adresse(
        str(row_eg.get("cdcommune_norm_eg", "")),
        str(row_etab.get("code_commune_norm_etab", "")),
        str(row_eg.get("nmvoie_norm_eg", "")),
        str(row_etab.get("numero_voie_norm_etab", "")),
        str(row_eg.get("libelle_voie_complet_eg", "")),
        str(row_etab.get("libelle_voie_complet_etab", "")),
    )
    s_glb = calc_score_global(s_nom, s_adr)

    return {
        "score_nom":          round(s_nom, 2),
        "score_adresse":      round(s_adr, 2),
        "score_global":       round(s_glb, 2),
        "nom_etab_retenu":    nom_etab,
    }


# ─── Phase 1 — matching SIRET exact ──────────────────────────────────────────

def matching_direct_siret(
    df_eg_clean: pd.DataFrame,
    df_etab_clean: pd.DataFrame,
    desc: str = "Matching direct SIRET",
    show_progress: bool = True,
) -> pd.DataFrame:
    """
    Phase 1 siretisation : pour chaque EG FINESS, lookup SIRET exact dans
    la base établissements SIRENE.

    Statuts produits :
        VALIDE_FORT / VALIDE / DOUTEUX / REJETE
        SANS_SIRET    : EG sans nmsiret_stru renseigné
        SIRET_INCONNU : SIRET FINESS absent de SIRENE
    """
    from tqdm.auto import tqdm
    from src.matching import classifier_resultat

    etab_idx = df_etab_clean.set_index("siret")
    resultats = []

    rows = df_eg_clean.iterrows()
    if show_progress:
        rows = tqdm(rows, total=len(df_eg_clean), desc=desc)

    for _, row_eg in rows:
        siret_eg = str(row_eg.get("nmsiret_stru", "") or "").strip().replace(" ", "")
        base = row_eg.to_dict()

        if not siret_eg or siret_eg in ("nan", "None"):
            resultats.append({**base,
                "siret_etab": None, "score_nom": None,
                "score_adresse": None, "score_global": None,
                "nom_etab_retenu": None, "statut": "SANS_SIRET"})
            continue

        if siret_eg not in etab_idx.index:
            resultats.append({**base,
                "siret_etab": siret_eg, "score_nom": None,
                "score_adresse": None, "score_global": None,
                "nom_etab_retenu": None, "statut": "SIRET_INCONNU"})
            continue

        row_etab = etab_idx.loc[siret_eg]
        if isinstance(row_etab, pd.DataFrame):
            row_etab = row_etab.iloc[0]
        scores = scorer_paire_eg_etab(row_eg, row_etab)
        statut = classifier_resultat(
            scores["score_global"], scores["score_nom"], scores["score_adresse"])
        resultats.append({**base, "siret_etab": siret_eg, **scores, "statut": statut})

    return pd.DataFrame(resultats)


# ─── Phase 3 : matching approfondi (APE + date d'établissement) ──────────────

from typing import Optional


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


def _normaliser_ape(code) -> str:
    if code is None or (isinstance(code, float) and pd.isna(code)):
        return ""
    return str(code).strip().upper().replace(".", "").replace(" ", "")


def _score_ape(ape_finess: str, ape_sirene: str) -> Optional[float]:
    a = _normaliser_ape(ape_finess)
    b = _normaliser_ape(ape_sirene)
    if not a or not b:
        return None
    if a == b:        return 100.0
    if a[:4] == b[:4]: return 70.0
    if a[:3] == b[:3]: return 40.0
    if a[:2] == b[:2]: return 20.0
    return 0.0


def _score_date(annee_finess: Optional[int], annee_sirene: Optional[int]) -> Optional[float]:
    if annee_finess is None or annee_sirene is None:
        return None
    ecart = abs(annee_finess - annee_sirene)
    if ecart <= 1:  return 100.0
    if ecart <= 3:  return 80.0
    if ecart <= 5:  return 60.0
    if ecart <= 10: return 40.0
    if ecart <= 20: return 20.0
    return 0.0


def scorer_paire_approfondi_eg(row_eg: pd.Series, row_etab: pd.Series) -> dict:
    """
    Scoring Phase 3 siretisation : reprend le scoring textuel + adresse,
    et ajoute APE et date de création d'établissement.

    Pour la siretisation, on utilise la dateCreationEtablissement (et non
    dateCreationUniteLegale) car on matche au niveau établissement.

    Pondération adaptative :
        - APE et date dispos : 0.70 × global + 0.20 × ape + 0.10 × date
        - APE seul           : 0.80 × global + 0.20 × ape
        - date seule         : 0.80 × global + 0.20 × date
        - aucun              : score_global standard
    """
    base = scorer_paire_eg_etab(row_eg, row_etab)

    s_ape   = _score_ape(row_eg.get("cdape_stru"), row_etab.get("activitePrincipaleUniteLegale"))
    annee_f = _extraire_annee(row_eg.get("dtouvertstruct_stru"))
    annee_s = _extraire_annee(row_etab.get("dateCreationEtablissement"))
    s_date  = _score_date(annee_f, annee_s)

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
        "annee_creation_eg":       annee_f,
        "annee_creation_etab":     annee_s,
        "ape_eg":                  _normaliser_ape(row_eg.get("cdape_stru")),
        "ape_etab":                _normaliser_ape(row_etab.get("activitePrincipaleUniteLegale")),
        "score_global_approfondi": round(s_glb_app, 2),
    }
