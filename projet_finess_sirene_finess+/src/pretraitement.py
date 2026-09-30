"""Normalisations textuelles et adresses, pour FINESS+ et SIRENE."""
import re
import sys
import unicodedata
from pathlib import Path
from typing import Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import STOP_WORDS, TYPE_VOIE_MAPPING, SENTINELLES


def normaliser_texte(texte: Optional[str]) -> str:
    """Majuscules, sans accents, sans ponctuation, espaces réduits."""
    if texte is None or (isinstance(texte, float) and pd.isna(texte)):
        return ""
    texte = str(texte).strip()
    if texte.lower() in SENTINELLES:
        return ""
    texte = texte.upper()
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


def pretraiter_libelle_voie(texte: Optional[str]) -> str:
    return supprimer_stopwords(normaliser_texte(texte))


def pretraiter_numero_voie(valeur) -> str:
    if valeur is None or (isinstance(valeur, float) and pd.isna(valeur)):
        return ""
    m = re.match(r"^(\d+)", str(valeur).strip())
    return m.group(1) if m else ""


def pretraiter_code_commune(valeur) -> str:
    """Code commune sur cinq caractères, lettres corses conservées.

    La Corse porte des codes en 2A et 2B. Les supprimer transformerait 2A004 en
    02004, soit un code de l'Aisne, et router­ait toute la Corse dans le mauvais
    département. La fonction s'applique des deux côtés — FINESS et SIRENE — pour
    que les codes restent comparables.
    """
    if valeur is None or (isinstance(valeur, float) and pd.isna(valeur)):
        return ""
    s = re.sub(r"[^0-9AB]", "", str(valeur).strip().upper())
    if not s:
        return ""
    return s.zfill(5) if len(s) < 5 else s[:5]


def extraire_dept(code_commune) -> str:
    if not code_commune:
        return "INCONNU"
    s = str(code_commune).zfill(5)
    return s[:3] if s.startswith(("97", "98")) else s[:2]


def extraire_siren(siret) -> str:
    """9 premiers chiffres du SIRET."""
    if siret is None or (isinstance(siret, float) and pd.isna(siret)):
        return ""
    s = re.sub(r"\s", "", str(siret).strip())
    return s[:9] if len(s) >= 9 else ""


def nettoyer_identifiant(valeur) -> str:
    """SIREN / SIRET / numéro FINESS : sans espaces, sans valeur sentinelle."""
    if valeur is None or (isinstance(valeur, float) and pd.isna(valeur)):
        return ""
    s = re.sub(r"\s", "", str(valeur).strip())
    return "" if s.lower() in SENTINELLES or s in ("nan", "None") else s


# ─── Prétraitement PM FINESS+ (sirenisation) ─────────────────────────────────

def pretraiter_pm(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise les personnes morales. Suffixe `_pm`."""
    df = df.copy()

    df["raisonsociale_norm_pm"] = df["TX_DenominationPm"].apply(pretraiter_denomination)
    df["nmvoie_norm_pm"]        = df["TX_NumeroVoie"].apply(pretraiter_numero_voie)
    df["lbtypevoie_norm_pm"]    = df["TX_TypeVoie"].apply(mapper_type_voie)
    df["lbvoie_norm_pm"]        = df["TX_LibelleVoie"].apply(pretraiter_libelle_voie)
    df["cdcommune_norm_pm"]     = df["TX_CogCommune"].apply(pretraiter_code_commune)
    df["dept_pm"]               = df["cdcommune_norm_pm"].apply(extraire_dept)
    df["siren_norm_pm"]         = df["TX_Siren"].apply(nettoyer_identifiant)
    df["finess_norm_pm"]        = df["TX_NumFinessPm"].apply(nettoyer_identifiant)

    df["libelle_voie_complet_pm"] = (
        df["lbtypevoie_norm_pm"] + " " + df["lbvoie_norm_pm"]
    ).str.strip()

    df["adresse_complete_pm"] = (
        df["TX_NumeroVoie"].fillna("").astype(str).str.strip()
        + " " + df["TX_TypeVoie"].fillna("").astype(str).str.strip()
        + " " + df["TX_LibelleVoie"].fillna("").astype(str).str.strip()
    ).str.strip().str.replace(r"\s+", " ", regex=True)

    return df


# ─── Prétraitement EGE FINESS+ (siretisation) ────────────────────────────────

def pretraiter_ege(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise les établissements. Suffixe `_ege`."""
    df = df.copy()

    df["raisonsociale_norm_ege"] = df["TX_NomEgeLong"].apply(pretraiter_denomination)
    df["nom_court_norm_ege"]     = df["TX_NomEgeCourt"].apply(pretraiter_denomination)
    df["nmvoie_norm_ege"]        = df["TX_NumeroVoie"].apply(pretraiter_numero_voie)
    df["lbtypevoie_norm_ege"]    = df["TX_TypeVoie"].apply(mapper_type_voie)
    df["lbvoie_norm_ege"]        = df["TX_LibelleVoie"].apply(pretraiter_libelle_voie)
    df["cdcommune_norm_ege"]     = df["TX_CogCommune"].apply(pretraiter_code_commune)
    df["dept_ege"]               = df["cdcommune_norm_ege"].apply(extraire_dept)
    df["siret_norm_ege"]         = df["TX_Siret"].apply(nettoyer_identifiant)
    df["siren_ege"]              = df["siret_norm_ege"].apply(extraire_siren)
    df["finess_norm_ege"]        = df["TX_NumFinessEge"].apply(nettoyer_identifiant)

    df["libelle_voie_complet_ege"] = (
        df["lbtypevoie_norm_ege"] + " " + df["lbvoie_norm_ege"]
    ).str.strip()

    df["adresse_complete_ege"] = (
        df["TX_NumeroVoie"].fillna("").astype(str).str.strip()
        + " " + df["TX_TypeVoie"].fillna("").astype(str).str.strip()
        + " " + df["TX_LibelleVoie"].fillna("").astype(str).str.strip()
    ).str.strip().str.replace(r"\s+", " ", regex=True)

    return df


# ─── Prétraitement SIRENE (inchangé) ─────────────────────────────────────────

def pretraiter_etab(df: pd.DataFrame) -> pd.DataFrame:
    """Établissements SIRENE. Suffixe `_etab`."""
    df = df.copy()

    df["denomination_norm_etab"]         = df["denominationUniteLegale"].apply(pretraiter_denomination)
    df["enseigne1_norm_etab"]            = df["enseigne1Etablissement"].apply(pretraiter_denomination)
    df["enseigne2_norm_etab"]            = df["enseigne2Etablissement"].apply(pretraiter_denomination)
    df["enseigne3_norm_etab"]            = df["enseigne3Etablissement"].apply(pretraiter_denomination)
    df["denomination_usuelle_norm_etab"] = df["denominationUsuelleEtablissement"].apply(pretraiter_denomination)

    df["numero_voie_norm_etab"]  = df["numeroVoieEtablissement"].apply(pretraiter_numero_voie)
    df["type_voie_norm_etab"]    = df["typeVoieEtablissement"].apply(mapper_type_voie)
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


def pretraiter_ul(df: pd.DataFrame) -> pd.DataFrame:
    """Unités légales SIRENE, adresse du siège déjà jointe. Suffixe `_ul`."""
    df = df.copy()

    df["denomination_norm_ul"] = df["denominationUniteLegale"].apply(pretraiter_denomination)
    df["sigle_norm_ul"]        = df.get("sigleUniteLegale",
                                        pd.Series("", index=df.index)).apply(pretraiter_denomination)

    df["numero_voie_norm_ul"]  = df["numeroVoieEtablissement"].apply(pretraiter_numero_voie)
    df["type_voie_norm_ul"]    = df["typeVoieEtablissement"].apply(mapper_type_voie)
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
