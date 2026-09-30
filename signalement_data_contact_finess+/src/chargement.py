"""Chargement des structures FINESS+ et de leurs coordonnées.

Dans l'ancien modèle, l'email et le téléphone étaient des colonnes de
`dwh_structure`. FINESS+ les porte dans une table `Telecom` atteinte par une
table de liaison : la requête enchaîne structure, liaison contact, telecom.

Les télécoms sont pivotés par canal — 2 téléphone, 3 mail, 6 télécopie — pour
qu'une structure reste sur une seule ligne. Sans ce pivot, un contact portant un
mail et un téléphone dédoublerait sa structure.

L'adresse suit le même chemin par sa propre table de liaison : elle sert à la
détection géographique des deux contrôles.

Le filtre `BL_VersionCourante = 1` est indispensable, sans lui chaque structure
remonte autant de fois qu'elle a de versions dans l'entrepôt.
"""
import re
import sys
import unicodedata
import warnings
from difflib import get_close_matches
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

warnings.filterwarnings("ignore", message=".*only supports SQLAlchemy.*")

SCHEMA = "dbo"
PREFIXES = ("T_FAC_", "T_DIM_", "T_Tmp_", "T_")

TABLES_LOGIQUES = {
    "pm":          "PM_SMSSE",
    "ege":         "EGE",
    "adresse":     "Adresse",
    "telecom":     "Telecom",
    "pm_adresse":  "PmSmsseAdresse",
    "ege_adresse": "EgeAdresse",
    "pm_contact":  "PmSmsseContact",
    "ege_contact": "EgeContact",
}

# TX_Canal porte un code numérique malgré le préfixe TX_.
LIBELLES_CANAL = {"2": "TELEPHONE", "3": "MAIL", "6": "TELECOPIE"}

SENTINELLES = {"non pertinent", "non rapproche", "non rapproché",
               "non renseigne", "non renseigné", "-1", "-2", "-3"}


def _normaliser(nom: str) -> str:
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
        f"SELECT name FROM sys.tables WHERE schema_id = SCHEMA_ID('{SCHEMA}')",
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
            f"Tables introuvables dans le schema {SCHEMA} :\n"
            + "\n".join(f"   {k} -> candidats {v}" for k, v in details.items())
            + "\nCorriger TABLES_LOGIQUES en tete de src/chargement.py.")

    for alias, reel in resolu.items():
        print(f"   {alias:<12} -> {reel}")
    return resolu


# ─── Requêtes ────────────────────────────────────────────────────────────────

def _requete_ege(tables: dict, actifs: bool) -> str:
    filtre = "AND e.TX_EtatActif = 'A'" if actifs else ""
    return f"""
    SELECT e.ID_Ege,
           e.NB_EgeId,
           e.NB_PmSmsseId,
           e.TX_NumFinessEge,
           e.TX_NomEgeLong,
           e.TX_CategorieEntiteGeographiqueExercice,
           e.TX_EtatActif,
           a.TX_NumeroVoie,
           a.TX_TypeVoie,
           a.TX_LibelleVoie,
           a.TX_CodePostal,
           a.TX_Localite,
           a.TX_CogCommune,
           lc.NB_ContactId
    FROM [{SCHEMA}].[{tables['ege']}] e
    LEFT JOIN [{SCHEMA}].[{tables['ege_adresse']}] la
           ON la.NB_EgeId = e.NB_EgeId AND la.BL_VersionCourante = 1
    LEFT JOIN [{SCHEMA}].[{tables['adresse']}] a
           ON a.NB_AdresseId = la.NB_AdresseId AND a.BL_VersionCourante = 1
    LEFT JOIN [{SCHEMA}].[{tables['ege_contact']}] lc
           ON lc.NB_EgeId = e.NB_EgeId AND lc.BL_VersionCourante = 1
    WHERE e.BL_VersionCourante = 1
      {filtre}
    """


def _requete_pm(tables: dict, actifs: bool) -> str:
    filtre = "AND p.TX_EtatActif = 'A'" if actifs else ""
    return f"""
    SELECT p.ID_PmSmsse,
           p.NB_PmSmsseId,
           p.TX_NumFinessPm,
           p.TX_DenominationPm,
           p.TX_CategorieEntiteGeographiqueExercice,
           p.TX_EtatActif,
           a.TX_NumeroVoie,
           a.TX_TypeVoie,
           a.TX_LibelleVoie,
           a.TX_CodePostal,
           a.TX_Localite,
           a.TX_CogCommune,
           lc.NB_ContactId
    FROM [{SCHEMA}].[{tables['pm']}] p
    LEFT JOIN [{SCHEMA}].[{tables['pm_adresse']}] la
           ON la.NB_PmSmsseId = p.NB_PmSmsseId AND la.BL_VersionCourante = 1
    LEFT JOIN [{SCHEMA}].[{tables['adresse']}] a
           ON a.NB_AdresseId = la.NB_AdresseId AND a.BL_VersionCourante = 1
    LEFT JOIN [{SCHEMA}].[{tables['pm_contact']}] lc
           ON lc.NB_PmSmsseId = p.NB_PmSmsseId AND lc.BL_VersionCourante = 1
    WHERE p.BL_VersionCourante = 1
      {filtre}
    """


def charger_telecoms(conn, tables: dict) -> pd.DataFrame:
    """Télécoms pivotés : une ligne par contact, une colonne par canal."""
    brut = pd.read_sql(f"""
        SELECT NB_ContactId, TX_Canal, TX_AdresseTelecom
        FROM [{SCHEMA}].[{tables['telecom']}]
        WHERE BL_VersionCourante = 1
          AND NB_ContactId IS NOT NULL
    """, conn)

    codes = brut["TX_Canal"].astype(str).str.strip()
    sentinelle = codes.str.lower().isin(SENTINELLES)
    if sentinelle.any():
        print(f"   {int(sentinelle.sum()):,} lignes de canal sentinelle ecartees")
        brut, codes = brut[~sentinelle], codes[~sentinelle]

    inconnus = sorted(set(codes) - set(LIBELLES_CANAL))
    if inconnus:
        print(f"   canaux non traduits, conserves sous CANAL_<code> : {inconnus}")
    brut["_canal"] = codes.map(LIBELLES_CANAL).fillna("CANAL_" + codes)

    multiples = int(brut.duplicated(subset=["NB_ContactId", "_canal"]).sum())
    if multiples:
        print(f"   {multiples:,} doublons (contact, canal) : premiere valeur conservee")

    pivot = (brut.pivot_table(index="NB_ContactId", columns="_canal",
                              values="TX_AdresseTelecom", aggfunc="first")
                 .reset_index())
    pivot.columns = ["NB_ContactId"] + [f"TEL_{c}" for c in pivot.columns[1:]]
    print(f"   telecoms pivotes : {len(pivot):,} contacts, "
          f"colonnes {list(pivot.columns[1:])}")
    return pivot


def _finaliser(df: pd.DataFrame, telecoms: pd.DataFrame, cle: str) -> pd.DataFrame:
    """Joint les télécoms, agrège les contacts, ajoute les colonnes dérivées.

    Une structure porte souvent plusieurs contacts, et ces contacts sont
    spécialisés : l'un le téléphone, l'autre le mail. On agrège donc les
    coordonnées de tous ses contacts en prenant la première valeur non nulle par
    canal, plutôt que de retenir un seul contact — ce qui perdrait les canaux
    portés par les autres.
    """
    colonnes_tel = [c for c in telecoms.columns if c != "NB_ContactId"]

    # même type des deux côtés, la jointure gauche introduit des NaN
    df["NB_ContactId"] = pd.to_numeric(df["NB_ContactId"], errors="coerce").astype("Int64")
    telecoms = telecoms.copy()
    telecoms["NB_ContactId"] = pd.to_numeric(telecoms["NB_ContactId"],
                                             errors="coerce").astype("Int64")

    avant = len(df)
    df = df.merge(telecoms, on="NB_ContactId", how="left")

    contacts = (df.groupby(cle)["NB_ContactId"].nunique()
                  .rename("nb_contacts").reset_index())
    coordonnees = (df.sort_values([cle, "NB_ContactId"], kind="mergesort")
                     .groupby(cle)[colonnes_tel].first()
                     .reset_index())

    base = (df.drop(columns=colonnes_tel + ["NB_ContactId"])
              .drop_duplicates(subset=[cle], keep="first"))
    df = base.merge(coordonnees, on=cle, how="left").merge(contacts, on=cle, how="left")
    df["nb_contacts"] = df["nb_contacts"].fillna(0).astype(int)

    print(f"   {avant:,} lignes -> {len(df):,} structures, "
          f"{df['nb_contacts'].max()} contacts au maximum pour une structure")

    for colonne in ("TEL_MAIL", "TEL_TELEPHONE", "TEL_TELECOPIE"):
        if colonne not in df.columns:
            df[colonne] = pd.NA

    df["adresse_complete"] = (
        df["TX_NumeroVoie"].fillna("").astype(str).str.strip() + " "
        + df["TX_TypeVoie"].fillna("").astype(str).str.strip() + " "
        + df["TX_LibelleVoie"].fillna("").astype(str).str.strip()
    ).str.replace(r"\s+", " ", regex=True).str.strip()

    df["departement"] = (df["TX_CogCommune"].fillna("").astype(str).str.strip().str[:2])
    return df


def charger_ege(conn, tables: dict, telecoms: pd.DataFrame,
                actifs_seulement: bool = True) -> pd.DataFrame:
    """Établissements avec adresse et coordonnées."""
    df = pd.read_sql(_requete_ege(tables, actifs_seulement), conn)
    print(f"   {len(df):,} lignes brutes")
    return _finaliser(df, telecoms, "NB_EgeId")


def charger_pm(conn, tables: dict, telecoms: pd.DataFrame,
               actifs_seulement: bool = True) -> pd.DataFrame:
    """Personnes morales avec adresse et coordonnées."""
    df = pd.read_sql(_requete_pm(tables, actifs_seulement), conn)
    print(f"   {len(df):,} lignes brutes")
    return _finaliser(df, telecoms, "NB_PmSmsseId")


def charger_categories_ege(conn, tables: dict) -> pd.DataFrame:
    """Catégorie et commune de tous les EGE actifs.

    Sert deux usages : la catégorie propre d'un EGE, et la remontée depuis les
    établissements fils pour les personnes morales.
    """
    df = pd.read_sql(f"""
        SELECT e.NB_EgeId, e.NB_PmSmsseId, e.TX_NumFinessEge,
               e.TX_CategorieEntiteGeographiqueExercice, a.TX_CogCommune
        FROM [{SCHEMA}].[{tables['ege']}] e
        LEFT JOIN [{SCHEMA}].[{tables['ege_adresse']}] la
               ON la.NB_EgeId = e.NB_EgeId AND la.BL_VersionCourante = 1
        LEFT JOIN [{SCHEMA}].[{tables['adresse']}] a
               ON a.NB_AdresseId = la.NB_AdresseId AND a.BL_VersionCourante = 1
        WHERE e.BL_VersionCourante = 1 AND e.TX_EtatActif = 'A'
    """, conn)
    return df.drop_duplicates(subset=["NB_EgeId"]).reset_index(drop=True)


def charger_categories_pm(conn, tables: dict) -> pd.DataFrame:
    """Catégorie propre des personnes morales, quand elle existe."""
    df = pd.read_sql(f"""
        SELECT NB_PmSmsseId, TX_NumFinessPm,
               TX_CategorieEntiteGeographiqueExercice
        FROM [{SCHEMA}].[{tables['pm']}]
        WHERE BL_VersionCourante = 1 AND TX_EtatActif = 'A'
    """, conn)
    return df.drop_duplicates(subset=["NB_PmSmsseId"]).reset_index(drop=True)
