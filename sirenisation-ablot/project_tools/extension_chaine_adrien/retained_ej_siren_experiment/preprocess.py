"""Preprocess the retained-EJ-SIREN Adrien experiment outputs."""

from __future__ import annotations

from pathlib import Path

from source_preprocessing.adrien import (
    prepare_adrien_candidates,
    prepare_adrien_ej,
    resolve_adrien_ege_duplicates,
)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"

INITIAL_INPUT = (
    RAW_DIR
    / "df_sirets_initiaux_avec_concordances_elargis_sirens_annotes_sample_only_2026_07.parquet"
)
PROPOSALS_INPUT = (
    RAW_DIR
    / "df_propositions_sirets_elargis_sirens_annotes_sample_only_2026_07.parquet"
)

EJ_OUTPUT = (
    DATA_DIR
    / "df_adrien_sirets_concordants_elargis_sirens_annotes_sample_only_2026_07_sirenise.parquet"
)
EGE_OUTPUT = (
    DATA_DIR
    / "df_adrien_sirets_concordants_elargis_sirens_annotes_sample_only_2026_07_clean.parquet"
)


def main() -> None:
    """Prepare the July 2026 experimental Adrien EJ and EGE datasets."""

    candidates = prepare_adrien_candidates(INITIAL_INPUT, PROPOSALS_INPUT)
    ege, _ = resolve_adrien_ege_duplicates(
        candidates,
        additional_source_flag_columns=("source_siret_prop_siren_ej_corrige",),
    )
    ej = prepare_adrien_ej(candidates)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ej.to_parquet(EJ_OUTPUT, index=False)
    ege.to_parquet(EGE_OUTPUT, index=False)

    print(f"adrien_ej: {EJ_OUTPUT}")
    print(f"adrien_ege: {EGE_OUTPUT}")


if __name__ == "__main__":
    main()
