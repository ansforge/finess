"""Normalisations textuelles et adresses (génériques pour FINESS et SIRENE)."""
import re
import sys
import unicodedata
from pathlib import Path
from typing import Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import STOP_WORDS, TYPE_VOIE_MAPPING


def normaliser_texte(texte: Optional[str]) -> str:
    """Majuscules + suppression accents/ponctuation/espaces multiples."""
    if texte is None or (isinstance(texte, float) and pd.isna(texte)):
        return ""
    texte = str(texte).strip().upper()
    texte = unicodedata.normalize("NFD", texte).encode("ascii", "ignore").decode("ascii")
    texte = re.sub(r"[^A-Z0-9\s]", " ", texte)
    return re.sub(r"\s+", " ", texte).strip()


def supprimer_stopwords(texte: str, stop_words: set = STOP_WORDS) -> str:
    if not texte:
        return ""
    return " ".join(t for t in texte.split() if t not in stop_words)


def mapper_type_voie(type_voie: Optional[str]) -> str:
    if not type_voie:
        return ""
    t = normaliser_texte(type_voie)
    return TYPE_VOIE_MAPPING.get(t, t)


def pretraiter_denomination(texte: Optional[str]) -> str:
    return supprimer_stopwords(normaliser_texte(texte))


def pretraiter_type_voie(texte: Optional[str]) -> str:
    return mapper_type_voie(texte)


def pretraiter_libelle_voie(texte: Optional[str]) -> str:
    return supprimer_stopwords(normaliser_texte(texte))


def pretraiter_numero_voie(valeur) -> str:
    if valeur is None or (isinstance(valeur, float) and pd.isna(valeur)):
        return ""
    s = str(valeur).strip()
    m = re.match(r"^(\d+)", s)
    return m.group(1) if m else ""


def pretraiter_code_commune(valeur) -> str:
    if valeur is None or (isinstance(valeur, float) and pd.isna(valeur)):
        return ""
    s = re.sub(r"\D", "", str(valeur).strip())
    return s.zfill(5) if s else ""


def extraire_dept(code_commune) -> str:
    if not code_commune:
        return "INCONNU"
    s = str(code_commune).zfill(5)
    if s.startswith(("97", "98")):
        return s[:3]
    return s[:2]


def extraire_siren(siret) -> str:
    """9 premiers chiffres du SIRET, sans espaces."""
    if siret is None or (isinstance(siret, float) and pd.isna(siret)):
        return ""
    s = re.sub(r"\s", "", str(siret).strip())
    return s[:9] if len(s) >= 9 else ""


# ─── Prétraitement EG FINESS (siretisation) ──────────────────────────────────

def pretraiter_eg(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise les champs textuels des EG FINESS. Suffixe _eg."""
    df = df.copy()

    df["raisonsociale_norm_eg"] = df["raisonsociale_stru"].apply(pretraiter_denomination)
    df["nmvoie_norm_eg"]        = df["nmvoie_stru"].apply(pretraiter_numero_voie)
    df["lbtypevoie_norm_eg"]    = df["lbtypevoie_stru"].apply(pretraiter_type_voie)
    df["lbvoie_norm_eg"]        = df["lbvoie_stru"].apply(pretraiter_libelle_voie)
    df["cdcommune_norm_eg"]     = df["cdcommune_stru"].apply(pretraiter_code_commune)
    df["dept_eg"]               = df["cdcommune_norm_eg"].apply(extraire_dept)
    df["siren_eg"]              = df["nmsiret_stru"].apply(extraire_siren)

    df["libelle_voie_complet_eg"] = (
        df["lbtypevoie_norm_eg"] + " " + df["lbvoie_norm_eg"]
    ).str.strip()

    df["adresse_complete_eg"] = (
        df["nmvoie_stru"].fillna("").astype(str).str.strip()
        + " " + df["lbtypevoie_stru"].fillna("").astype(str).str.strip()
        + " " + df["lbvoie_stru"].fillna("").astype(str).str.strip()
    ).str.strip().str.replace(r"\s+", " ", regex=True)

    return df


# ─── Prétraitement EJ FINESS (sirenisation) ──────────────────────────────────

def pretraiter_ej(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise les champs textuels des EJ FINESS. Suffixe _ej."""
    df = df.copy()

    df["raisonsociale_norm_ej"] = df["raisonsociale_stru"].apply(pretraiter_denomination)
    df["nmvoie_norm_ej"]        = df["nmvoie_stru"].apply(pretraiter_numero_voie)
    df["lbtypevoie_norm_ej"]    = df["lbtypevoie_stru"].apply(pretraiter_type_voie)
    df["lbvoie_norm_ej"]        = df["lbvoie_stru"].apply(pretraiter_libelle_voie)
    df["cdcommune_norm_ej"]     = df["cdcommune_stru"].apply(pretraiter_code_commune)
    df["dept_ej"]               = df["cdcommune_norm_ej"].apply(extraire_dept)

    df["libelle_voie_complet_ej"] = (
        df["lbtypevoie_norm_ej"] + " " + df["lbvoie_norm_ej"]
    ).str.strip()

    df["adresse_complete_ej"] = (
        df["nmvoie_stru"].fillna("").astype(str).str.strip()
        + " " + df["lbtypevoie_stru"].fillna("").astype(str).str.strip()
        + " " + df["lbvoie_stru"].fillna("").astype(str).str.strip()
    ).str.strip().str.replace(r"\s+", " ", regex=True)

    return df


# ─── Prétraitement Etab SIRENE (siretisation) ────────────────────────────────

def pretraiter_etab(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise les champs textuels des établissements SIRENE. Suffixe _etab."""
    df = df.copy()

    df["denomination_norm_etab"]         = df["denominationUniteLegale"].apply(pretraiter_denomination)
    df["enseigne1_norm_etab"]            = df["enseigne1Etablissement"].apply(pretraiter_denomination)
    df["enseigne2_norm_etab"]            = df["enseigne2Etablissement"].apply(pretraiter_denomination)
    df["enseigne3_norm_etab"]            = df["enseigne3Etablissement"].apply(pretraiter_denomination)
    df["denomination_usuelle_norm_etab"] = df["denominationUsuelleEtablissement"].apply(pretraiter_denomination)

    df["numero_voie_norm_etab"]  = df["numeroVoieEtablissement"].apply(pretraiter_numero_voie)
    df["type_voie_norm_etab"]    = df["typeVoieEtablissement"].apply(pretraiter_type_voie)
    df["libelle_voie_norm_etab"] = df["libelleVoieEtablissement"].apply(pretraiter_libelle_voie)
    df["code_commune_norm_etab"] = df["codeCommuneEtablissement"].apply(pretraiter_code_commune)
    df["dept_etab"]              = df["code_commune_norm_etab"].apply(extraire_dept)

    df["libelle_voie_complet_etab"] = (
        df["type_voie_norm_etab"] + " " + df["libelle_voie_norm_etab"]
    ).str.strip()

    df["adresse_complete_etab"] = (
        df["numeroVoieEtablissement"].fillna("").astype(str).str.strip()
        + " " + df["typeVoieEtablissement"].fillna("").astype(str).str.strip()
        + " " + df["libelleVoieEtablissement"].fillna("").astype(str).str.strip()
    ).str.strip().str.replace(r"\s+", " ", regex=True)

    return df


# ─── Prétraitement UL SIRENE (sirenisation) ──────────────────────────────────

def pretraiter_ul(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise les UL SIRENE (avec adresse siège déjà jointe). Suffixe _ul."""
    df = df.copy()

    df["denomination_norm_ul"] = df["denominationUniteLegale"].apply(pretraiter_denomination)
    df["sigle_norm_ul"]        = df.get("sigleUniteLegale", pd.Series(dtype=str)).apply(pretraiter_denomination)

    df["numero_voie_norm_ul"]  = df["numeroVoieEtablissement"].apply(pretraiter_numero_voie)
    df["type_voie_norm_ul"]    = df["typeVoieEtablissement"].apply(pretraiter_type_voie)
    df["libelle_voie_norm_ul"] = df["libelleVoieEtablissement"].apply(pretraiter_libelle_voie)
    df["code_commune_norm_ul"] = df["codeCommuneEtablissement"].apply(pretraiter_code_commune)
    df["dept_ul"]              = df["code_commune_norm_ul"].apply(extraire_dept)

    df["libelle_voie_complet_ul"] = (
        df["type_voie_norm_ul"] + " " + df["libelle_voie_norm_ul"]
    ).str.strip()

    df["adresse_siege_complete_ul"] = (
        df["numeroVoieEtablissement"].fillna("").astype(str).str.strip()
        + " " + df["typeVoieEtablissement"].fillna("").astype(str).str.strip()
        + " " + df["libelleVoieEtablissement"].fillna("").astype(str).str.strip()
    ).str.strip().str.replace(r"\s+", " ", regex=True)

    return df
