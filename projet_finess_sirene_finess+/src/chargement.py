"""Chargement des personnes morales et des établissements FINESS+."""
import re
import sys
import unicodedata
import warnings
from difflib import get_close_matches
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import DB_SCHEMA

# pyodbc n'est pas un connectable SQLAlchemy : l'avertissement est sans effet ici
warnings.filterwarnings("ignore", message=".*only supports SQLAlchemy.*")

PREFIXES = ("T_FAC_", "T_DIM_", "T_Tmp_", "T_")

# Noms logiques attendus, tels qu'ils figurent au macro-modele.
TABLES_LOGIQUES = {
    "pm":          "PM_SMSSE",
    "ege":         "EGE",
    "adresse":     "Adresse",
    "pm_adresse":  "PmSmsseAdresse",
    "ege_adresse": "EgeAdresse",
    "evenement":   "Evenement",
    "telecom":     "Telecom",
    "pm_contact":  "PmSmsseContact",
    "ege_contact": "EgeContact",
}

# TX_Canal porte un code numérique malgré son préfixe TX_.
LIBELLES_CANAL = {"2": "TELEPHONE", "3": "MAIL", "6": "TELECOPIE"}

SENTINELLES = {"non pertinent", "non rapproche", "non rapproché",
               "non renseigne", "non renseigné", "-1", "-2", "-3"}


def _normaliser(nom: str) -> str:
    """T_FAC_PmSmsseAdresse et PM_SMSSE_adresse donnent la meme cle."""
    nom = unicodedata.normalize("NFKD", str(nom)).encode("ascii", "ignore").decode()
    for p in PREFIXES:
        if nom.upper().startswith(p.upper()):
            nom = nom[len(p):]
            break
    return re.sub(r"[^a-z0-9]", "", nom.lower())


def resoudre_tables(conn, logiques: dict | None = None) -> dict:
    """Associe chaque nom logique à son nom technique réel.

    Les tables de staging T_Tmp_ sont écartées. En cas d'échec, l'erreur liste
    les candidats les plus proches.
    """
    logiques = logiques or TABLES_LOGIQUES

    catalogue = pd.read_sql(
        f"SELECT name FROM sys.tables WHERE schema_id = SCHEMA_ID('{DB_SCHEMA}')",
        conn)["name"].tolist()
    exploitables = [t for t in catalogue if not t.upper().startswith("T_TMP_")]

    index = {}
    for t in exploitables:
        index.setdefault(_normaliser(t), t)

    resolu, manquantes = {}, []
    for alias, logique in logiques.items():
        cle = _normaliser(logique)
        if cle in index:
            resolu[alias] = index[cle]
        else:
            manquantes.append((alias, logique))

    if manquantes:
        details = {}
        for alias, logique in manquantes:
            proches = get_close_matches(_normaliser(logique), list(index), n=5, cutoff=0.4)
            details[f"{alias} ({logique})"] = [index[p] for p in proches]
        raise RuntimeError(
            f"Tables introuvables dans le schema {DB_SCHEMA} :\n"
            + "\n".join(f"   {k} -> candidats {v}" for k, v in details.items())
            + "\nCorriger TABLES_LOGIQUES en tete de src/chargement.py."
        )

    for alias, reel in resolu.items():
        print(f"   {alias:<12} -> {reel}")
    return resolu


# ─── Requetes ────────────────────────────────────────────────────────────────

def _requete_pm(tables: dict, filtre_actif: str) -> str:
    return f"""
    SELECT p.ID_PmSmsse,
           p.NB_PmSmsseId,
           p.TX_NumFinessPm,
           p.TX_Siren,
           p.TX_DenominationPm,
           p.TX_DenominationLonguePmSmsse,
           p.TX_ComplementAdressePmSmsse,
           p.TX_CategorieEntiteGeographiqueExercice,
           p.TX_StatutJuridique,
           p.TX_TypePersonneMorale,
           p.TX_EtatActif,
           p.FK_MetadonneeId,
           p.NB_EntrepriseInseeId,
           l.TX_UsageAdresse,
           a.NB_AdresseId,
           a.TX_TypeAdresse,
           a.TX_NumeroVoie,
           a.TX_TypeVoie,
           a.TX_LibelleVoie,
           a.TX_ComplementPointGeographique,
           a.TX_LieuDit,
           a.TX_CodePostal,
           a.TX_Localite,
           a.TX_CogCommune
    FROM [{DB_SCHEMA}].[{tables['pm']}] p
    LEFT JOIN [{DB_SCHEMA}].[{tables['pm_adresse']}] l
           ON l.NB_PmSmsseId = p.NB_PmSmsseId AND l.BL_VersionCourante = 1
    LEFT JOIN [{DB_SCHEMA}].[{tables['adresse']}] a
           ON a.NB_AdresseId = l.NB_AdresseId AND a.BL_VersionCourante = 1
    WHERE p.BL_VersionCourante = 1
      {filtre_actif}
    """


def _requete_ege(tables: dict, filtre_actif: str) -> str:
    return f"""
    SELECT e.ID_Ege,
           e.NB_EgeId,
           e.NB_PmSmsseId,
           e.TX_NumFinessEge,
           e.TX_Siret,
           e.TX_NomEgeLong,
           e.TX_NomEgeCourt,
           e.TX_ComplementDenominationEg,
           e.TX_CategorieEntiteGeographiqueExercice,
           e.TX_EtatActif,
           e.FK_MetadonneeId,
           e.NB_EtablissementInseeId,
           l.TX_UsageAdresse,
           a.NB_AdresseId,
           a.TX_TypeAdresse,
           a.TX_NumeroVoie,
           a.TX_TypeVoie,
           a.TX_LibelleVoie,
           a.TX_ComplementPointGeographique,
           a.TX_LieuDit,
           a.TX_CodePostal,
           a.TX_Localite,
           a.TX_CogCommune
    FROM [{DB_SCHEMA}].[{tables['ege']}] e
    LEFT JOIN [{DB_SCHEMA}].[{tables['ege_adresse']}] l
           ON l.NB_EgeId = e.NB_EgeId AND l.BL_VersionCourante = 1
    LEFT JOIN [{DB_SCHEMA}].[{tables['adresse']}] a
           ON a.NB_AdresseId = l.NB_AdresseId AND a.BL_VersionCourante = 1
    WHERE e.BL_VersionCourante = 1
      {filtre_actif}
    """


def charger_pm(conn, tables: dict, actifs_seulement: bool = True) -> pd.DataFrame:
    """Personnes morales avec leur adresse."""
    filtre = "AND p.TX_EtatActif = 'A'" if actifs_seulement else ""
    return pd.read_sql(_requete_pm(tables, filtre), conn)


def charger_ege(conn, tables: dict, actifs_seulement: bool = True) -> pd.DataFrame:
    """Etablissements avec leur adresse."""
    filtre = "AND e.TX_EtatActif = 'A'" if actifs_seulement else ""
    return pd.read_sql(_requete_ege(tables, filtre), conn)


def charger_dates_ouverture_pm(conn, tables: dict) -> pd.DataFrame:
    """Dates d'ouverture des personnes morales, depuis la table Evenement.

    Seuls les événements de code 001 portant sur une PM sont retenus. Une
    structure pouvant en compter plusieurs, on garde la date la plus ancienne.
    """
    from config.settings import CODE_EVENEMENT_OUVERTURE, TYPE_OBJET_PM

    requete = f"""
        SELECT TX_NumeroFINESSObjet1 AS finess,
               MIN(DT_DateEvenement)  AS date_ouverture,
               COUNT(*)               AS nb_evenements
        FROM [{DB_SCHEMA}].[{tables['evenement']}]
        WHERE TX_CodeEvenement = '{CODE_EVENEMENT_OUVERTURE}'
          AND TX_TypeObjet1 = '{TYPE_OBJET_PM}'
          AND TX_NumeroFINESSObjet1 IS NOT NULL
          AND LEN(TX_NumeroFINESSObjet1) >= 8
        GROUP BY TX_NumeroFINESSObjet1
    """
    df = pd.read_sql(requete, conn)
    multiples = int((df["nb_evenements"] > 1).sum())
    print(f"   {len(df):,} PM avec une date d'ouverture"
          + (f", dont {multiples:,} avec plusieurs evenements 001" if multiples else ""))
    return df


def charger_contacts(conn, tables: dict, niveau: str) -> pd.DataFrame:
    """Coordonnées d'un niveau de structure, une ligne par structure.

    Les coordonnées ne sont pas des colonnes de la structure : elles vivent dans
    la table Telecom, atteinte par une table de liaison. Elles sont pivotées par
    canal, puis agrégées sur tous les contacts d'une structure — ceux-ci sont
    souvent spécialisés, l'un portant le téléphone et l'autre le mail.
    """
    if niveau not in ("pm", "ege"):
        raise ValueError("niveau doit valoir 'pm' ou 'ege'")

    cle = "NB_PmSmsseId" if niveau == "pm" else "NB_EgeId"
    table_structure = tables["pm"] if niveau == "pm" else tables["ege"]
    table_liaison = tables["pm_contact"] if niveau == "pm" else tables["ege_contact"]

    brut = pd.read_sql(f"""
        SELECT s.{cle}, t.TX_Canal, t.TX_AdresseTelecom
        FROM [{DB_SCHEMA}].[{table_structure}] s
        JOIN [{DB_SCHEMA}].[{table_liaison}] l
          ON l.{cle} = s.{cle} AND l.BL_VersionCourante = 1
        JOIN [{DB_SCHEMA}].[{tables['telecom']}] t
          ON t.NB_ContactId = l.NB_ContactId AND t.BL_VersionCourante = 1
        WHERE s.BL_VersionCourante = 1
          AND t.TX_AdresseTelecom IS NOT NULL
    """, conn)

    if brut.empty:
        print(f"   aucune coordonnee trouvee pour les {niveau.upper()}")
        return pd.DataFrame(columns=[cle, "TEL_MAIL", "TEL_TELEPHONE", "TEL_TELECOPIE"])

    codes = brut["TX_Canal"].astype(str).str.strip()
    brut = brut[~codes.str.lower().isin(SENTINELLES)]
    codes = codes[brut.index]
    brut["_canal"] = codes.map(LIBELLES_CANAL).fillna("CANAL_" + codes)

    pivot = (brut.pivot_table(index=cle, columns="_canal",
                              values="TX_AdresseTelecom", aggfunc="first")
                 .reset_index())
    pivot.columns = [cle] + [f"TEL_{c}" for c in pivot.columns[1:]]

    for colonne in ("TEL_MAIL", "TEL_TELEPHONE", "TEL_TELECOPIE"):
        if colonne not in pivot.columns:
            pivot[colonne] = pd.NA

    print(f"   {len(pivot):,} {niveau.upper()} avec au moins une coordonnee "
          f"({int(pivot['TEL_MAIL'].notna().sum()):,} mail, "
          f"{int(pivot['TEL_TELEPHONE'].notna().sum()):,} telephone)")
    return pivot


def colonnes_disponibles(conn, nom_table: str) -> list:
    """Colonnes reelles d'une table, pour diagnostiquer une requete en echec."""
    return pd.read_sql(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        f"WHERE TABLE_SCHEMA = '{DB_SCHEMA}' AND TABLE_NAME = '{nom_table}' "
        "ORDER BY ORDINAL_POSITION", conn)["COLUMN_NAME"].tolist()


# ─── Reduction a une ligne par structure ─────────────────────────────────────

def dedupliquer(df: pd.DataFrame, cle: str,
                usage_prioritaire: str | None = None) -> pd.DataFrame:
    """Une ligne par structure quand plusieurs adresses sont rattachées.

    usage_prioritaire privilégie un type d'adresse ; à défaut on garde la
    première, ordonnée par NB_AdresseId pour rester reproductible.
    """
    avant = len(df)
    df = df.copy()
    df["_priorite"] = 0
    if usage_prioritaire and "TX_UsageAdresse" in df.columns:
        df.loc[df["TX_UsageAdresse"] == usage_prioritaire, "_priorite"] = -1

    tri = ["_priorite"] + [c for c in ("NB_AdresseId",) if c in df.columns]
    df = (df.sort_values([cle] + tri, kind="mergesort")
            .drop_duplicates(subset=[cle], keep="first")
            .drop(columns=["_priorite"])
            .reset_index(drop=True))

    if avant != len(df):
        print(f"   deduplication sur {cle} : {avant:,} -> {len(df):,} lignes")
    return df
