#!/usr/bin/env python
# coding: utf-8

# In[11]:


get_ipython().system('pip install pyodbc pandas duckdb pathlib')


# In[12]:


import os
import pyodbc
import duckdb
import pandas as pd
from typing import Dict
from pathlib import Path


# In[21]:


# =========================================================
# CONFIG
# =========================================================

SQL_SERVER_CONFIG: Dict[str, str] = {
    "driver": "ODBC Driver 17 for SQL Server",
    "server": "PRD-DBDW-P01.soclebi-prod.esante.gouv.fr",
    "database": "BICOEUR_DWH_SNAPSHOT",
    "trusted_connection": "yes",
}

try:
    BASE_DIR = Path(__file__).resolve().parent
except NameError:
    BASE_DIR = Path.cwd()

# dossier des fichiers Sirene: UL + ET
SIRENE_DIR = BASE_DIR.parent / "sirene"

FILES = {
    "unite_legale": SIRENE_DIR / "StockUniteLegale.parquet",
    "etablissement": SIRENE_DIR / "StockEtablissement.parquet",
}

DUCKDB_PATH = BASE_DIR / "sirene.duckdb"
# =========================================================
# Se connecter à SQL Server
# =========================================================

def connect_sql_server(config: Dict[str, str]):
    """Connexion SQL Server"""
    try:
        conn_str = (
            f"DRIVER={{{config['driver']}}};"
            f"SERVER={config['server']};"
            f"DATABASE={config['database']};"
            f"Trusted_Connection={config['trusted_connection']};"
        )

        conn = pyodbc.connect(conn_str)
        print("✅ Connexion SQL Server réussie")
        return conn

    except Exception as e:
        print("Erreur connexion SQL Server :", e)
        return None


# =========================================================
# se connecter à DUCKDB
# =========================================================
def connect_duckdb(db_path: Path, read_only=True):
    """Connexion DuckDB sécurisée"""
    try:
        con = duckdb.connect(database=db_path, read_only=read_only)
        mode = "Lecture" if read_only else "Ecriture"
        print(f"✅ Connexion DuckDB ({mode}) : {db_path}")
        return con

    except Exception as e:
        raise RuntimeError(f" Connexion DuckDB échouée : {e}")

# =========================================================
# Vérifier si une table existe
# =========================================================
def table_exists(con, table_name: str) -> bool:
    """Vérifie si une table existe dans DuckDB"""
    query = f"""
    SELECT COUNT(*)
    FROM information_schema.tables
    WHERE table_name = '{table_name}'
    """
    return con.execute(query).fetchone()[0] > 0

# =========================================================
# LOADERS SIRENE
# =========================================================

def load_unite_legale(con, file_path: Path, force=False):
    """Charge la table unite_legale, dont l'étatAdministratif = actif  uniquement si absente (ou force=True)"""

    if table_exists(con, "sirene_unite_legale") and not force:
        print("Table sirene_unite_legale déjà existante → skip")
        return

    print(" Création de sirene_unite_legale...")

    con.execute(f"""
    CREATE OR REPLACE TABLE sirene_unite_legale AS
    SELECT 
        CAST(siren AS VARCHAR) AS siren,
        CAST(nicSiegeUniteLegale AS VARCHAR) AS nic,
        LOWER(TRIM(CAST(denominationUniteLegale AS VARCHAR))) AS denomination,
        CAST(etatAdministratifUniteLegale AS VARCHAR) AS etat_adm,
        CAST(categorieJuridiqueUniteLegale AS VARCHAR) AS categorie_jur,
        CAST(activitePrincipaleUniteLegale AS VARCHAR) AS activite_principale
    FROM read_parquet('{file_path}')
    WHERE CAST(etatAdministratifUniteLegale AS VARCHAR) = 'A'
    """)

    print("✅ Table sirene_unite_legale créée")

#------------------------------------------------------
#------------------------------------------------------

def load_etablissement(con, file_path: Path, force=False):
    """Charge la table etablissement, dont l'étatAdministratif = actif uniquement si absente (ou force=True)"""

    if table_exists(con, "sirene_etablissement") and not force:
        print(" Table sirene_etablissement déjà existante → skip")
        return

    print(" Création de sirene_etablissement...")

    con.execute(f"""
    CREATE OR REPLACE TABLE sirene_etablissement AS
    SELECT 
        CAST(siren AS VARCHAR) AS siren,
        CAST(nic AS VARCHAR) AS nic,
        CAST(siret AS VARCHAR) AS siret,
        CAST(etablissementSiege AS VARCHAR) AS etablissement_siege,       
        CAST(numeroVoieEtablissement AS VARCHAR) AS numero_voie,
        LOWER(TRIM(CAST(typeVoieEtablissement AS VARCHAR))) AS type_voie,
        LOWER(TRIM(CAST(libelleVoieEtablissement AS VARCHAR))) AS libelle_voie,
        CAST(codePostalEtablissement AS VARCHAR) AS code_postal,
        CAST(codeCommuneEtablissement AS VARCHAR) AS code_commune,
        CAST(etatAdministratifEtablissement AS VARCHAR) AS etat_adm
    FROM read_parquet('{file_path}')
    WHERE CAST(etablissementSiege AS VARCHAR) = 'true'
      AND CAST(etatAdministratifEtablissement AS VARCHAR) = 'A'
    """)

    print("✅ Table sirene_etablissement créée")


# =========================================================
# JOIN SIRENE (UL + EG)
# =========================================================

# => Force = true, force la reconstruction de la table à nouveau

def join_sirene(con, force=False):
    """Jointure UL + ETAB uniquement si absente (ou force=True)"""

    if table_exists(con, "sirene_joined") and not force:
        print(" Table sirene_joined déjà existante → skip")
        return

    print(" Création de sirene_joined...")

    con.execute("""
    CREATE OR REPLACE TABLE sirene_joined AS
    SELECT 
        -- clés
        et.siret,
        ul.siren,
        ul.nic,
        denomination,

        -- localisation
        et.code_commune,
        et.code_postal,

        -- adresse détaillée
        et.numero_voie,
        et.type_voie,
        et.libelle_voie,

        -- adresse complète 
        UPPER(TRIM(
            COALESCE(et.numero_voie, '') || ' ' ||
            COALESCE(et.type_voie, '') || ' ' ||
            COALESCE(et.libelle_voie, '')
        )) AS adresse_complete

    FROM sirene_unite_legale ul
    INNER JOIN sirene_etablissement et
        ON ul.siren = et.siren
       AND ul.nic = et.nic
    """)

    print("✅ Table sirene_joined créée")

#------------------------------------------------------
#------------------------------------------------------

# Counts utiles sur les tables sirene:

def counts(con):
    print("UL :", con.execute("SELECT COUNT(*) FROM sirene_unite_legale").fetchone()[0])
    print("ETAB :", con.execute("SELECT COUNT(*) FROM sirene_etablissement").fetchone()[0])
    print("JOIN :", con.execute("SELECT COUNT(*) FROM sirene_joined").fetchone()[0])

# ============================================================================================
# FONCTIONS_PRINCIPALES: get_finess_active(), count_finess_active(), get_sirene_active()
# ============================================================================================
def get_finess_active():
    """Retourne une connexion SQL Server avec EJ active"""

    conn = connect_sql_server(SQL_SERVER_CONFIG)

    if conn is None:
        return None

    return conn

#------------------------------------------------------
#------------------------------------------------------

def count_finess_active(conn) -> int:
    """Nombre d'EJ FINESS ouvertes"""

    query = """
    SELECT COUNT(idstructure_stru) AS nb
    FROM BICOEUR_DWH_SNAPSHOT.dbo.dwh_structure
    WHERE topsource_stru = 'FINESS'
      AND typeidpm_stru = 'EJ'
      AND (
            dtfermestruct_stru IS NULL
            OR dtfermestruct_stru >= SYSDATETIME()
      )
    """

    try:
        df = pd.read_sql(query, conn)
        count = int(df["nb"].iloc[0])
        print(f"Nombre d'EJ ouvertes : {count}")
        return count

    except Exception as e:
        print("Erreur lecture FINESS :", e)
        return None

#------------------------------------------------------
#------------------------------------------------------

def get_sirene_active(read_only= True, force_reload=False):
    """
    Connexion DuckDB + création des tables si nécessaire

    read_only = True → lecture uniquement
    force_reload = True → reconstruit toutes les tables
    """


    # si DB n'existe pas → forcer WRITE
    if read_only and not os.path.exists(DUCKDB_PATH):
        print(" DB inexistante → création en mode WRITE")
        read_only = False

    con = connect_duckdb(DUCKDB_PATH, read_only=read_only)

    if con is None:
        raise ConnectionError("Connexion DuckDB échouée")

    # ---uniquement en mode écriture---
    if not read_only:
        # 1. Load
        load_unite_legale(con, FILES["unite_legale"], force=force_reload)
        load_etablissement(con, FILES["etablissement"], force=force_reload)
        # 2. Join
        join_sirene(con, force=force_reload)
        # 3. Vérification
        counts(con)

    return con

# --- read_only=True → lecture / read_only=False → écriture ---

# In[ ]:




