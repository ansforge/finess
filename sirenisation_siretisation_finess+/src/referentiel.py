"""Référentiel APE et date d'ouverture, source de la phase 3."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    REFERENTIELS_DIR, REF_MOTIFS, REF_COL_CLE, REF_COL_APE, REF_COL_DATE,
    REF_SEPARATEUR, REF_ENCODAGES,
)
from src.pretraitement import nettoyer_identifiant
from src.scoring import extraire_annee, normaliser_ape

COL_CLE = "cle_referentiel"
COL_APE = "ape_referentiel"
COL_ANNEE = "annee_referentiel"


def _trouver(motif: str) -> Path | None:
    fichiers = sorted(REFERENTIELS_DIR.glob(motif), reverse=True)
    return fichiers[0] if fichiers else None


def _lire(chemin: Path) -> pd.DataFrame:
    for encodage in REF_ENCODAGES:
        try:
            return pd.read_csv(chemin, sep=REF_SEPARATEUR, encoding=encodage, dtype=str)
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"Encodage non reconnu pour {chemin.name}")


def _dates_pm_evenement() -> pd.DataFrame | None:
    """Dates d'ouverture des PM, extraites de la table Evenement par le notebook 01."""
    from config.settings import EVENEMENTS_PM

    if not EVENEMENTS_PM.exists():
        print(f"   date  {EVENEMENTS_PM.name} absent, executer d'abord le notebook 01")
        return None

    brut = pd.read_parquet(EVENEMENTS_PM)
    part = pd.DataFrame({
        COL_CLE: brut["finess"].map(nettoyer_identifiant),
        COL_ANNEE: brut["date_ouverture"].map(extraire_annee),
    })
    part = part[(part[COL_CLE] != "") & part[COL_ANNEE].notna()]
    part = part.drop_duplicates(subset=[COL_CLE])
    print(f"   date  {EVENEMENTS_PM.name} : {len(part):,} PM")
    return part


def charger_referentiel(niveau: str) -> pd.DataFrame:
    """Référentiel d'un niveau ('pm' ou 'ege'), une ligne par numéro FINESS."""
    if niveau not in ("pm", "ege"):
        raise ValueError("niveau doit valoir 'pm' ou 'ege'")

    print(f"Referentiel {niveau.upper()}")
    parties = []

    chemin = _trouver(REF_MOTIFS[(niveau, "ape")])
    if chemin is None:
        print(f"   ape   aucun fichier pour {REF_MOTIFS[(niveau, 'ape')]}")
    else:
        brut = _lire(chemin)
        part = pd.DataFrame({COL_CLE: brut[REF_COL_CLE].map(nettoyer_identifiant)})
        part[COL_APE] = brut[REF_COL_APE].map(normaliser_ape)
        part = part[(part[COL_CLE] != "") & (part[COL_APE] != "")]
        part = part.drop_duplicates(subset=[COL_CLE])
        print(f"   ape   {chemin.name} : {len(brut):,} lignes, {len(part):,} exploitables")
        parties.append(part)

    if niveau == "pm":
        part = _dates_pm_evenement()
        if part is not None:
            parties.append(part)
    else:
        chemin = _trouver(REF_MOTIFS[(niveau, "date")])
        if chemin is None:
            print(f"   date  aucun fichier pour {REF_MOTIFS[(niveau, 'date')]}")
        else:
            brut = _lire(chemin)
            part = pd.DataFrame({COL_CLE: brut[REF_COL_CLE].map(nettoyer_identifiant)})
            part[COL_ANNEE] = brut[REF_COL_DATE].map(extraire_annee)
            part = part[(part[COL_CLE] != "") & part[COL_ANNEE].notna()]
            part = part.drop_duplicates(subset=[COL_CLE])
            print(f"   date  {chemin.name} : {len(brut):,} lignes, {len(part):,} exploitables")
            parties.append(part)

    if not parties:
        print("   referentiel vide, la phase 3 s'executera sans APE ni date")
        return pd.DataFrame(columns=[COL_CLE, COL_APE, COL_ANNEE])

    ref = parties[0]
    for part in parties[1:]:
        ref = ref.merge(part, on=COL_CLE, how="outer")
    if COL_APE not in ref:
        ref[COL_APE] = ""
    if COL_ANNEE not in ref:
        ref[COL_ANNEE] = pd.NA
    ref[COL_APE] = ref[COL_APE].fillna("")

    print(f"   total {len(ref):,} structures, {(ref[COL_APE] != '').sum():,} avec APE, "
          f"{ref[COL_ANNEE].notna().sum():,} avec annee")
    return ref[[COL_CLE, COL_APE, COL_ANNEE]].reset_index(drop=True)


def enrichir(df: pd.DataFrame, col_finess: str, niveau: str,
             referentiel: pd.DataFrame | None = None) -> pd.DataFrame:
    """Ajoute ape_referentiel et annee_referentiel à une table de structures."""
    df = df.copy()
    if referentiel is None:
        referentiel = charger_referentiel(niveau)

    if referentiel.empty:
        df[COL_APE] = ""
        df[COL_ANNEE] = pd.NA
        return df

    df["_cle"] = df[col_finess].map(nettoyer_identifiant)
    df = (df.merge(referentiel, how="left", left_on="_cle", right_on=COL_CLE)
            .drop(columns=["_cle", COL_CLE], errors="ignore"))
    df[COL_APE] = df[COL_APE].fillna("")

    print(f"Enrichissement {niveau.upper()} sur {len(df):,} lignes : "
          f"APE {(df[COL_APE] != '').mean() * 100:.1f} %, "
          f"annee {df[COL_ANNEE].notna().mean() * 100:.1f} %")
    return df


def diagnostiquer() -> pd.DataFrame:
    """Inventaire des fichiers présents, à consulter avant la phase 3."""
    lignes = []
    for (niveau, genre), motif in REF_MOTIFS.items():
        chemin = _trouver(motif)
        if chemin is None:
            lignes.append({"niveau": niveau, "type": genre, "fichier": "ABSENT",
                           "lignes": 0, "renseignes": 0, "colonnes": "",
                           "exemples": ""})
            continue
        brut = _lire(chemin)
        colonne = REF_COL_APE if genre == "ape" else REF_COL_DATE
        valeurs = brut[colonne].dropna() if colonne in brut else pd.Series(dtype=str)
        lignes.append({
            "niveau": niveau, "type": genre, "fichier": chemin.name,
            "lignes": len(brut), "renseignes": len(valeurs),
            "colonnes": " | ".join(brut.columns),
            "exemples": " | ".join(
                f"{c}={v}" for c, v in zip(brut[REF_COL_CLE].head(3),
                                           brut[colonne].head(3).fillna("(vide)"))),
        })
    return pd.DataFrame(lignes)
