from __future__ import annotations

from pathlib import Path

import build_dev_data
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEV_SOURCE = ROOT / "dev/data/source"


def test_dev_source_slice_is_relationally_closed():
    finess_ej = pd.read_parquet(
        DEV_SOURCE
        / "finess_entites_juridiques/EntitesJuridiques_2026_05_04.parquet",
        columns=["nofiness"],
    )
    finess_ege = pd.read_parquet(
        DEV_SOURCE
        / "finess_etablissements/EtablissementsGeolocalises_2026_05_04.parquet",
        columns=["nofinesset", "nofinessej"],
    )

    seed_ejs = set(finess_ej["nofiness"].map(build_dev_data.canonical).dropna())
    assert seed_ejs == set(build_dev_data.SEED_EJS)
    assert not finess_ege.empty
    assert set(
        finess_ege["nofinessej"].map(build_dev_data.canonical).dropna()
    ).issubset(seed_ejs)

    source_frames = [
        finess_ej,
        finess_ege,
        pd.read_parquet(DEV_SOURCE / "ANS/df_ans_ej_valides.parquet"),
        pd.read_parquet(DEV_SOURCE / "ANS/df_ans_ege_valides.parquet"),
        pd.read_parquet(
            DEV_SOURCE
            / "Adrien_Tortel/df_adrien_sirets_concordants_2026_06_sirenise.parquet"
        ),
        pd.read_parquet(
            DEV_SOURCE
            / "Adrien_Tortel/df_adrien_sirets_concordants_2026_06_clean.parquet"
        ),
    ]
    sirens, sirets = build_dev_data.business_references(source_frames)

    units = pd.read_parquet(
        DEV_SOURCE / "sirene_unites_legales/StockUniteLegale_2026_06_01.parquet",
        columns=["siren"],
    )
    establishments_june = pd.read_parquet(
        DEV_SOURCE / "sirene_etablissements/StockEtablissement_2026_06_01.parquet",
        columns=["siret"],
    )
    establishments_july = pd.read_parquet(
        DEV_SOURCE / "sirene_etablissements/StockEtablissement_2026_07_01.parquet",
        columns=["siret"],
    )

    available_sirets = (
        build_dev_data.identifiers(establishments_june["siret"], 14)
        | build_dev_data.identifiers(establishments_july["siret"], 14)
    )
    assert sirets.issubset(available_sirets)
    assert sirens.issubset(build_dev_data.identifiers(units["siren"], 9))
