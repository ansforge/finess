"""Connexions FINESS (SQL Server) et SIRENE (DuckDB sur parquets)."""
import sys
from pathlib import Path

import pyodbc
import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import DB_SERVER, DB_DATABASE, DB_DRIVER, PARQUET_UL, PARQUET_ETAB


def get_finess_connection() -> pyodbc.Connection:
    """Connexion ODBC à BICOEUR_DWH_SNAPSHOT via Citrix."""
    conn_str = (
        f"DRIVER={{{DB_DRIVER}}};"
        f"SERVER={DB_SERVER};"
        f"DATABASE={DB_DATABASE};"
        "Trusted_Connection=yes;"
    )
    return pyodbc.connect(conn_str)


def get_duckdb_connection(
    ul_path: Path | str = PARQUET_UL,
    etab_path: Path | str = PARQUET_ETAB,
) -> duckdb.DuckDBPyConnection:
    """
    Connexion DuckDB avec vues SIRENE pré-enregistrées.

    Vues exposées :
        ul          : unités légales brutes
        etab        : établissements bruts
        ul_active   : unités légales actives (avec date de création)
        etab_active : établissements actifs avec dénomination UL et enseignes
        etab_siege  : sous-ensemble des établissements actifs qui sont siège
                      (pour récupérer l'adresse de l'UL)
    """
    con = duckdb.connect()
    con.execute(f"CREATE VIEW ul   AS SELECT * FROM read_parquet('{ul_path}')")
    con.execute(f"CREATE VIEW etab AS SELECT * FROM read_parquet('{etab_path}')")

    con.execute("""
        CREATE VIEW ul_active AS
        SELECT siren, nicSiegeUniteLegale,
               denominationUniteLegale, sigleUniteLegale,
               categorieJuridiqueUniteLegale, activitePrincipaleUniteLegale,
               dateCreationUniteLegale,
               etatAdministratifUniteLegale
        FROM ul
        WHERE etatAdministratifUniteLegale = 'A'
    """)

    # Établissements actifs avec dénomination UL et enseignes (pour siretisation)
    con.execute("""
        CREATE VIEW etab_active AS
        SELECT ul_active.siren,
               ul_active.nicSiegeUniteLegale,
               ul_active.denominationUniteLegale,
               ul_active.sigleUniteLegale,
               ul_active.categorieJuridiqueUniteLegale,
               ul_active.activitePrincipaleUniteLegale,
               ul_active.dateCreationUniteLegale,
               etab.nic, etab.siret,
               etab.etablissementSiege,
               etab.dateCreationEtablissement,
               etab.enseigne1Etablissement, etab.enseigne2Etablissement,
               etab.enseigne3Etablissement,
               etab.denominationUsuelleEtablissement,
               etab.numeroVoieEtablissement, etab.typeVoieEtablissement,
               etab.libelleVoieEtablissement, etab.codeCommuneEtablissement
        FROM ul_active
        INNER JOIN etab
            ON ul_active.siren = etab.siren
        WHERE etab.etatAdministratifEtablissement = 'A'
    """)

    # Sièges uniquement (pour sirenisation : adresse de l'UL)
    con.execute("""
        CREATE VIEW etab_siege AS
        SELECT *
        FROM etab_active
        WHERE etablissementSiege = 'true'
    """)

    return con
