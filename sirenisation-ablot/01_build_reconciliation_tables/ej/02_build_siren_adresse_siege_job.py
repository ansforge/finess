"""Add SIRENE head-office addresses to the base EJ proposal table.

For each distinct proposed SIREN, this job reads the corresponding head-office
establishment from the SIRENE stock, builds a readable address, and appends
``sirene__adresse_siege`` without changing the existing proposal rows or columns.
The enriched table is consumed by the final EJ denomination-completion job.
"""

from __future__ import annotations


def run() -> None:
    from pathlib import Path

    import pandas as pd

    from project_config import PATHS

    DATA_ROOT = PATHS.data
    RESULTS_ROOT = PATHS.results


    SAVE_OUTPUT = True
    OVERWRITE_OUTPUT = True

    OUTPUT_DIR = RESULTS_ROOT / "01_build_reconciliation_tables" / "ej"
    BASE_PROPOSAL_PATH = OUTPUT_DIR / "ej_siren_proposals_01_base.parquet"
    OUTPUT_PATH = OUTPUT_DIR / "ej_siren_proposals_with_head_office_address.parquet"

    SIRET_PATH = (
        DATA_ROOT
        / "sirene_etablissements"
        / "StockEtablissement_2026_06_01.parquet"
    )

    PROPOSAL_SIREN_COLUMN = "siren_proposal"
    SIRET_SIREN_COLUMN = "siren"
    HEAD_OFFICE_COLUMN = "etablissementSiege"
    OUTPUT_ADDRESS_COLUMN = "sirene__adresse_siege"

    ADDRESS_COLUMNS = [
        "complementAdresseEtablissement",
        "numeroVoieEtablissement",
        "indiceRepetitionEtablissement",
        "typeVoieEtablissement",
        "libelleVoieEtablissement",
        "distributionSpecialeEtablissement",
        "codePostalEtablissement",
        "libelleCommuneEtablissement",
        "libelleCommuneEtrangerEtablissement",
        "libelleCedexEtablissement",
        "libellePaysEtrangerEtablissement",
    ]

    def normalize_siren(series: pd.Series) -> pd.Series:
        """Normalize SIREN values to nullable, stripped strings."""
        return (
            series.astype("string")
            .str.strip()
            .replace({"": pd.NA, "N/A": pd.NA})
        )


    def build_address_column(df: pd.DataFrame) -> pd.Series:
        """Build the SIRENE head-office address with vectorized string operations."""
        parts = df.loc[:, ADDRESS_COLUMNS].astype("string").fillna("")
        parts = parts.apply(lambda column: column.str.strip())

        address = parts[ADDRESS_COLUMNS[0]]
        for column in ADDRESS_COLUMNS[1:]:
            address = address.str.cat(parts[column], sep=" ")

        return address.str.replace(r"\s+", " ", regex=True).str.strip()


    def check_output_permission(path: Path) -> None:
        if path.exists() and not OVERWRITE_OUTPUT:
            raise FileExistsError(
                f"{path} already exists and OVERWRITE_OUTPUT is False."
            )


    def write_parquet_table(df: pd.DataFrame, path: Path) -> None:
        """Write values without attempting to serialize custom DataFrame attrs."""
        export_df = df.copy()
        export_df.attrs = {}
        export_df.to_parquet(path, index=False)

    base_proposals = pd.read_parquet(BASE_PROPOSAL_PATH)

    if PROPOSAL_SIREN_COLUMN not in base_proposals.columns:
        raise KeyError(
            f"{BASE_PROPOSAL_PATH} does not contain "
            f"{PROPOSAL_SIREN_COLUMN!r}."
        )

    normalized_proposals = normalize_siren(
        base_proposals[PROPOSAL_SIREN_COLUMN]
    )

    proposed_sirens = (
        normalized_proposals
        .dropna()
        .drop_duplicates()
        .sort_values()
        .tolist()
    )


    SIRET_LOAD_COLUMNS = [
        SIRET_SIREN_COLUMN,
        HEAD_OFFICE_COLUMN,
        *ADDRESS_COLUMNS,
    ]

    if proposed_sirens:
        main_siret = pd.read_parquet(
            SIRET_PATH,
            columns=SIRET_LOAD_COLUMNS,
            filters=[
                (HEAD_OFFICE_COLUMN, "==", True),
                (SIRET_SIREN_COLUMN, "in", proposed_sirens),
            ],
        )
    else:
        main_siret = pd.DataFrame(columns=SIRET_LOAD_COLUMNS)

    main_siret[SIRET_SIREN_COLUMN] = normalize_siren(
        main_siret[SIRET_SIREN_COLUMN]
    )

    # Keep this check even though the same condition is used as a parquet filter.
    main_siret = main_siret.loc[
        main_siret[HEAD_OFFICE_COLUMN].eq(True)
    ].copy()


    main_siret[OUTPUT_ADDRESS_COLUMN] = build_address_column(main_siret)

    duplicate_head_offices = main_siret[SIRET_SIREN_COLUMN].duplicated(
        keep=False
    )
    if duplicate_head_offices.any():
        duplicate_count = main_siret.loc[
            duplicate_head_offices,
            SIRET_SIREN_COLUMN,
        ].nunique()
        print(
            "Warning: "
            f"{duplicate_count:,} SIREN(s) have multiple head-office rows; "
            "the first row is retained."
        )

    main_siret = main_siret.drop_duplicates(
        subset=[SIRET_SIREN_COLUMN],
        keep="first",
    )

    address_by_siren = main_siret.set_index(
        SIRET_SIREN_COLUMN
    )[OUTPUT_ADDRESS_COLUMN]

    # Drop a stale address column, if present, so the rebuilt variable is appended last.
    final_proposals = base_proposals.drop(
        columns=[OUTPUT_ADDRESS_COLUMN],
        errors="ignore",
    ).copy()

    final_proposals[OUTPUT_ADDRESS_COLUMN] = normalized_proposals.map(
        address_by_siren
    )


    if len(final_proposals) != len(base_proposals):
        raise ValueError("The address enrichment changed the number of proposal rows.")

    base_columns_without_address = [
        column
        for column in base_proposals.columns
        if column != OUTPUT_ADDRESS_COLUMN
    ]
    if final_proposals.columns[:-1].tolist() != base_columns_without_address:
        raise ValueError(
            "The base proposal variables or their order changed during enrichment."
        )

    if final_proposals.columns[-1] != OUTPUT_ADDRESS_COLUMN:
        raise ValueError(
            f"{OUTPUT_ADDRESS_COLUMN!r} must be the final variable."
        )

    valid_proposal_mask = normalized_proposals.notna()


    matched_sirens = normalized_proposals.map(address_by_siren).notna()
    proposal_rows_with_address = int(
        final_proposals.loc[
            valid_proposal_mask,
            OUTPUT_ADDRESS_COLUMN,
        ].notna().sum()
    )
    proposal_rows_without_address = int(
        final_proposals.loc[
            valid_proposal_mask,
            OUTPUT_ADDRESS_COLUMN,
        ].isna().sum()
    )
    print(
        "Head-office address enrichment: "
        f"{len(base_proposals):,} proposal rows; "
        f"{len(proposed_sirens):,} distinct proposed SIREN; "
        f"{matched_sirens.groupby(normalized_proposals).max().sum():,.0f} SIREN matched; "
        f"{proposal_rows_with_address:,} rows with address; "
        f"{proposal_rows_without_address:,} without."
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if SAVE_OUTPUT:
        check_output_permission(OUTPUT_PATH)
        write_parquet_table(final_proposals, OUTPUT_PATH)
        print(f"Saved: {OUTPUT_PATH}")
    else:
        print("SAVE_OUTPUT is False; no file was written.")


if __name__ == "__main__":
    run()