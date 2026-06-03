"""Configuration projet finess_sirene v1 — siretisation P1 + sirenisation complète."""
from pathlib import Path

# ─── Chemins ─────────────────────────────────────────────────────────────────
ROOT_DIR      = Path(__file__).resolve().parent.parent
DATA_DIR      = ROOT_DIR / "data"
RAW_DIR       = DATA_DIR / "raw"
INTERIM_DIR   = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
RESULTS_DIR   = ROOT_DIR / "results"

# Sources brutes
SIRENE_RAW_DIR = RAW_DIR / "sirene"
PARQUET_UL     = SIRENE_RAW_DIR / "StockUniteLegale_utf8.parquet"
PARQUET_ETAB   = SIRENE_RAW_DIR / "StockEtablissement_utf8.parquet"

# Données intermédiaires (parquets)
FINESS_EG_RAW    = INTERIM_DIR / "finess_eg.parquet"
FINESS_EJ_RAW    = INTERIM_DIR / "finess_ej.parquet"
SIRENE_ETAB_RAW  = INTERIM_DIR / "sirene_etab.parquet"
SIRENE_UL_RAW    = INTERIM_DIR / "sirene_ul.parquet"

# Données prétraitées
FINESS_EG_CLEAN   = PROCESSED_DIR / "finess_eg_clean.parquet"
FINESS_EJ_CLEAN   = PROCESSED_DIR / "finess_ej_clean.parquet"
SIRENE_ETAB_CLEAN = PROCESSED_DIR / "sirene_etab_clean.parquet"
SIRENE_ETAB_FILTRE = PROCESSED_DIR / "sirene_etab_filtre.parquet"
SIRENE_UL_CLEAN   = PROCESSED_DIR / "sirene_ul_clean.parquet"

# Sorties Siretisation
RESULTS_ST_DIR = RESULTS_DIR / "siretisation"
ST_PHASE1      = RESULTS_ST_DIR / "siretisation_phase1.xlsx"
ST_PHASE2      = RESULTS_ST_DIR / "siretisation_phase2_top5.xlsx"
ST_PHASE3      = RESULTS_ST_DIR / "siretisation_phase3_approfondi.xlsx"
ST_PERIMETRE   = PROCESSED_DIR / "siretisation_perimetre.parquet"

# Sorties Sirenisation
RESULTS_SN_DIR     = RESULTS_DIR / "sirenisation"
SN_PHASE1          = RESULTS_SN_DIR / "sirenisation_phase1.xlsx"
SN_PERIMETRE       = PROCESSED_DIR / "sirenisation_perimetre_abc.parquet"
SN_PHASE2          = RESULTS_SN_DIR / "sirenisation_phase2_top5.xlsx"
SN_PHASE3          = RESULTS_SN_DIR / "sirenisation_phase3_approfondi.xlsx"

# ─── Seuils de validation et poids de scoring (échelle 0–100) ────────────────
SEUIL_GLOBAL      = 67
SEUIL_NOM_MIN     = 15
SEUIL_ADRESSE_MIN = 55

# ─── Connexion SQL Server FINESS (Citrix) ────────────────────────────────────
DB_SERVER   = "PRD-DBDW-P01.soclebi-prod.esante.gouv.fr"
DB_DATABASE = "BICOEUR_DWH_SNAPSHOT"
DB_DRIVER   = "ODBC Driver 17 for SQL Server"

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
    "AV": "AVENUE",    "AVE": "AVENUE",
    "BD": "BOULEVARD", "BLD": "BOULEVARD", "BVD": "BOULEVARD",
    "PL": "PLACE",
    "RTE": "ROUTE",
    "ALL": "ALLEE",    "ALE": "ALLEE",
    "IMP": "IMPASSE",
    "CHE": "CHEMIN",   "CHEM": "CHEMIN",
    "QUA": "QUAI",
    "PAS": "PASSAGE",
    "PRO": "PROMENADE",
    "SQ":  "SQUARE",
    "PARC": "PARC",
    "VOIE": "VOIE",
    "VLA": "VILLAGE",
}

# Sorties Comparaison (cohérence SIREN ↔ SIRET)
RESULTS_COMP_DIR = RESULTS_DIR / "comparaison"
COMP_FINAL       = RESULTS_COMP_DIR / "coherence_siren_siret.xlsx"
COMP_PHASE1      = RESULTS_COMP_DIR / "coherence_phase1.xlsx"
COMP_PHASE2      = RESULTS_COMP_DIR / "coherence_phase2.xlsx"
COMP_PHASE3      = RESULTS_COMP_DIR / "coherence_phase3.xlsx"
COMP_GLOBALE     = RESULTS_COMP_DIR / "coherence_globale.xlsx"
