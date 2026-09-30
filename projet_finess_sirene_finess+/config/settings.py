"""Configuration projet finess_plus_sirene — siretisation, sirenisation, cohérence.

Modèle source : FINESS+ (BIFINESS_DWH_SNAPSHOT), remplace dwh_structure.
"""
from pathlib import Path

# ─── Chemins ─────────────────────────────────────────────────────────────────
ROOT_DIR      = Path(__file__).resolve().parent.parent
DATA_DIR      = ROOT_DIR / "data"
RAW_DIR       = DATA_DIR / "raw"
INTERIM_DIR   = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
REFERENTIELS_DIR = DATA_DIR / "referentiels"
RESULTS_DIR   = ROOT_DIR / "results"

# Sources brutes SIRENE (parquets INSEE déposés manuellement)
SIRENE_RAW_DIR = RAW_DIR / "sirene"
PARQUET_UL     = SIRENE_RAW_DIR / "StockUniteLegale_utf8.parquet"
PARQUET_ETAB   = SIRENE_RAW_DIR / "StockEtablissement_utf8.parquet"

# Données intermédiaires
FINESS_EGE_RAW  = INTERIM_DIR / "finess_ege.parquet"
FINESS_PM_RAW   = INTERIM_DIR / "finess_pm.parquet"
SIRENE_ETAB_RAW = INTERIM_DIR / "sirene_etab.parquet"
SIRENE_UL_RAW   = INTERIM_DIR / "sirene_ul.parquet"

# Données prétraitées
FINESS_EGE_CLEAN  = PROCESSED_DIR / "finess_ege_clean.parquet"
FINESS_PM_CLEAN   = PROCESSED_DIR / "finess_pm_clean.parquet"
SIRENE_ETAB_CLEAN = PROCESSED_DIR / "sirene_etab_clean.parquet"
SIRENE_UL_CLEAN   = PROCESSED_DIR / "sirene_ul_clean.parquet"

# Versions partitionnées par département : indispensables aux phases 2 et 3.
# Le blocking étant départemental, on lit un département à la fois au lieu de
# charger 15 millions de lignes en mémoire.
SIRENE_ETAB_PARTITIONNE = PROCESSED_DIR / "sirene_etab_clean_par_dept"

# Échantillon SIRENE réduit aux SIREN issus de la sirenisation, utilisé par les
# phases 2 et 3 de la siretisation (voir ST-02bis).
SIRENE_ETAB_FILTRE = PROCESSED_DIR / "sirene_etab_filtre.parquet"
SIRENE_ETAB_FILTRE_PARTITIONNE = PROCESSED_DIR / "sirene_etab_filtre_par_dept"
SIRENE_UL_PARTITIONNE   = PROCESSED_DIR / "sirene_ul_clean_par_dept"

# Sorties siretisation
RESULTS_ST_DIR = RESULTS_DIR / "siretisation"
ST_PHASE1      = RESULTS_ST_DIR / "siretisation_phase1.xlsx"
ST_PHASE2      = RESULTS_ST_DIR / "siretisation_phase2_top5.xlsx"
ST_PHASE3      = RESULTS_ST_DIR / "siretisation_phase3_approfondi.xlsx"
ST_PERIMETRE   = PROCESSED_DIR / "siretisation_perimetre.parquet"
ST_VALIDES_P1  = PROCESSED_DIR / "siretisation_valides_p1.parquet"
ST_VALIDES_P2  = PROCESSED_DIR / "siretisation_valides_p2.parquet"

# Sorties sirenisation
RESULTS_SN_DIR = RESULTS_DIR / "sirenisation"
SN_PHASE1      = RESULTS_SN_DIR / "sirenisation_phase1.xlsx"
SN_PHASE2      = RESULTS_SN_DIR / "sirenisation_phase2_top5.xlsx"
SN_PHASE3      = RESULTS_SN_DIR / "sirenisation_phase3_approfondi.xlsx"
SN_PERIMETRE   = PROCESSED_DIR / "sirenisation_perimetre_abc.parquet"
SN_PHASE1BIS   = RESULTS_SN_DIR / "sirenisation_phase1bis.xlsx"
SN_VALIDES_P1  = PROCESSED_DIR / "sirenisation_valides_p1.parquet"
SN_VALIDES_P2  = PROCESSED_DIR / "sirenisation_valides_p2.parquet"

# Sorties comparaison (cohérence SIREN ↔ SIRET, sur P1 + P2 + P3)
RESULTS_COMP_DIR = RESULTS_DIR / "comparaison"
COMP_GLOBALE     = RESULTS_COMP_DIR / "coherence_globale.xlsx"
COMP_PAR_PHASE   = RESULTS_COMP_DIR / "coherence_par_phase.xlsx"

# Revue manuelle DREES : vérité terrain du modèle de fiabilité.
DREES_DIR = DATA_DIR / "drees"
LOGIT_DIR = RESULTS_DIR / "model_logit"

# ─── Référentiel APE / date d'ouverture ──────────────────────────────────────
# FINESS+ ne porte ni code APE ni date d'ouverture. La phase 3 s'appuie sur
# quatre extractions déposées dans data/referentiels/, deux par niveau, au format
# "nofiness;codeape" ou "nofiness;dateouvert".
REF_MOTIFS = {
    ("pm", "ape"):   "Extraction_PM_codeape*.csv",
    ("pm", "date"):  "Extraction_PM_datecreat*.csv",
    ("ege", "ape"):  "Extraction_EG_codeape*.csv",
    ("ege", "date"): "Extraction_EG_dateouverture*.csv",
}
REF_COL_CLE  = "nofiness"
REF_COL_APE  = "codeape"
REF_COL_DATE = "dateouvert"
# Les dates d'ouverture des PM viennent de la table Evenement, code 001, et non
# d'un fichier : Extraction_PM_datecreat*.csv n'est plus utilisé.
EVENEMENTS_PM = INTERIM_DIR / "evenements_ouverture_pm.parquet"
CODE_EVENEMENT_OUVERTURE = "001"
TYPE_OBJET_PM = "PM"

REF_SEPARATEUR = ";"
REF_ENCODAGES = ("utf-8-sig", "latin-1")

# ─── Seuils de validation ────────────────────────────────────────────────────
SEUIL_GLOBAL      = 67
# ou 
SEUIL_NOM_MIN     = 15
SEUIL_ADRESSE_MIN = 55

# ─── Bonus identifiant cohérent (phases 2 et 3) ──────────────────────────────
BONUS_IDENTIFIANT_COHERENT = 15.0

# ─── Performance ─────────────────────────────────────────────────────────────
# Le scoring vectorisé construit des matrices nb_lignes_lot × nb_candidats_bloc.
# BUDGET_MEMOIRE_GO borne la taille des lots ; le résultat est identique quelle
# que soit la valeur, seul le découpage change.
BUDGET_MEMOIRE_GO = 4.0
N_MATRICES_PIC    = 12       # matrices float64 coexistant au pic, marge incluse
TAILLE_CHUNK_PARQUET = 500_000

# ─── Connexion SQL Server FINESS+ (Citrix) ───────────────────────────────────
DB_SERVER   = "PRD-DBDW-P01.soclebi-prod.esante.gouv.fr"
DB_DATABASE = "BIFINESS_DWH_SNAPSHOT"
DB_DRIVER   = "ODBC Driver 17 for SQL Server"
DB_SCHEMA   = "dbo"

# ─── Stop words métier (formes juridiques, liaisons) ─────────────────────────
STOP_WORDS = {
    "SA", "SAS", "SARL", "EURL", "SCI", "SELARL", "SELAS",
    "SCOP", "SNC", "EARL", "GIE", "SCA", "SEP", "SEMU",
    "ASSOCIATION", "ASSO",
    "DE", "DU", "DES", "LA", "LE", "LES", "ET", "EN",
    "AU", "AUX", "L", "D", "UN", "UNE", "PAR", "POUR", "SUR", "A",
}

# ─── Mapping type de voie ────────────────────────────────────────────────────
TYPE_VOIE_MAPPING = {
    "R": "RUE", "RUE": "RUE",
    "AV": "AVENUE", "AVE": "AVENUE", "AVENUE": "AVENUE",
    "BD": "BOULEVARD", "BLD": "BOULEVARD", "BVD": "BOULEVARD", "BO": "BOULEVARD",
    "BOULEVARD": "BOULEVARD",
    "PL": "PLACE", "PLC": "PLACE", "PLACE": "PLACE",
    "RTE": "ROUTE", "ROUTE": "ROUTE",
    "ALL": "ALLEE", "ALE": "ALLEE", "ALLEE": "ALLEE", "ALLEES": "ALLEE",
    "IMP": "IMPASSE", "IMPASSE": "IMPASSE",
    "CHE": "CHEMIN", "CHEM": "CHEMIN", "CH": "CHEMIN", "CHEMIN": "CHEMIN",
    "QUA": "QUAI", "QAI": "QUAI", "QU": "QUAI", "QUAI": "QUAI",
    "PAS": "PASSAGE", "PSG": "PASSAGE", "PGE": "PASSAGE", "PASSAGE": "PASSAGE",
    "PRO": "PROMENADE", "PROM": "PROMENADE", "PROMENADE": "PROMENADE",
    "SQ": "SQUARE", "SQUARE": "SQUARE",
    "COUR": "COURS", "CRS": "COURS", "CR": "COURS", "COURS": "COURS",
    "CHS": "CHAUSSEE", "CHAUSSEE": "CHAUSSEE",
    "FG": "FAUBOURG", "FBG": "FAUBOURG", "FAUBOURG": "FAUBOURG",
    "RPT": "ROND POINT", "RDPT": "ROND POINT", "ROND POINT": "ROND POINT",
    "MTE": "MONTEE", "MONTEE": "MONTEE",
    "SEN": "SENTIER", "STE": "SENTIER", "SENTE": "SENTIER", "SENTIER": "SENTIER",
    "TRA": "TRAVERSE", "TSSE": "TRAVERSE", "TRAVERSE": "TRAVERSE",
    "VLA": "VILLA", "VILLA": "VILLA",
    "VLGE": "VILLAGE", "VILLAGE": "VILLAGE",
    "RES": "RESIDENCE", "RSD": "RESIDENCE", "RESIDENCE": "RESIDENCE",
    "LOT": "LOTISSEMENT", "LOTISSEMENT": "LOTISSEMENT",
    "HAM": "HAMEAU", "HLE": "HAMEAU", "HAMEAU": "HAMEAU",
    "GR": "GRANDE RUE", "GRAND RUE": "GRANDE RUE", "GRANDE RUE": "GRANDE RUE",
    "PTE": "PORTE", "PORTE": "PORTE",
    "CAR": "CARREFOUR", "CARREFOUR": "CARREFOUR",
    "QUART": "QUARTIER", "QTR": "QUARTIER", "QUARTIER": "QUARTIER",
    "ESP": "ESPLANADE", "ESPLANADE": "ESPLANADE",
    "PARV": "PARVIS", "PARVIS": "PARVIS",
    "CITE": "CITE",
    "DOM": "DOMAINE", "DOMAINE": "DOMAINE",
    "ZA": "ZONE ARTISANALE", "ZI": "ZONE INDUSTRIELLE", "ZAC": "ZAC",
    "VOIE": "VOIE",
    "PARC": "PARC",
    "RPE": "RAMPE", "RAMPE": "RAMPE",
    "RLE": "RUELLE", "RUELLE": "RUELLE",
}

# ─── Valeurs sentinelles du DWH FINESS+ ──────────────────────────────────────
# Présentes sur toutes les colonnes de nomenclature (codes -1, -2, -3).
SENTINELLES = {"non pertinent", "non rapproche", "non rapproché",
               "non renseigne", "non renseigné", "-1", "-2", "-3"}

# Table de passage des codes géographiques, utilisée par la phase 0 du
# prétraitement pour valider les codes commune avant le matching.
COG_TABLE_PASSAGE      = REFERENTIELS_DIR / "table_passage_geo2003_geo2026.xlsx"

REFERENTIEL_CATEGORIES = REFERENTIELS_DIR / "FINESS_Categories_etablissements_V3_Ouverts.csv"
ROUTAGE_DIR = RESULTS_DIR / "routage"
