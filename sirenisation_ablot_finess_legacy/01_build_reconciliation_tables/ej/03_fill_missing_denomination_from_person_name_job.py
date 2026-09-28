"""Complete missing SIRENE denominations and publish final EJ proposals.

This job runs after the head-office address enrichment. For proposed SIREN values
whose legal-unit denomination is missing, it uses the person's first and last name
from the SIRENE legal-unit stock when available, then publishes the final Stage 01
EJ proposal table consumed by Stage 02.
"""

from __future__ import annotations


def run(
    *, write_output: bool = True, display_outputs: bool = True
) -> dict[str, object]:
    import pandas as pd

    from project_config import PATHS

    log = print if display_outputs else lambda *_args, **_kwargs: None

    RESULTS_DIR = PATHS.results / "01_build_reconciliation_tables/ej"
    INPUT_PATH = (
        RESULTS_DIR
        / "ej_siren_proposals_with_head_office_address.parquet"
    )
    OUTPUT_PATH = RESULTS_DIR / "ej_siren_proposals.parquet"
    STOCK_PATH = (
        PATHS.data
        / "sirene_unites_legales"
        / "StockUniteLegale_2026_06_01.parquet"
    )

    SIREN_COLUMN = "siren_proposal"
    DENOMINATION_COLUMN = "sirene__denominationUniteLegale"

    STOCK_SIREN_COLUMN = "siren"
    FIRST_NAME_COLUMN = "prenom1UniteLegale"
    LAST_NAME_COLUMN = "nomUniteLegale"

    def normalize_siren(series: pd.Series) -> pd.Series:
        """Normalize SIREN values to nullable nine-character strings."""
        normalized = (
            series.astype("string")
            .str.strip()
            .replace({"": pd.NA, "N/A": pd.NA})
        )
        numeric = normalized.str.fullmatch(r"\d{1,9}", na=False)
        normalized.loc[numeric] = normalized.loc[numeric].str.zfill(9)
        return normalized

    proposals = pd.read_parquet(INPUT_PATH)

    required_proposal_columns = {SIREN_COLUMN, DENOMINATION_COLUMN}
    missing = required_proposal_columns.difference(proposals.columns)
    if missing:
        raise KeyError(
            f"{INPUT_PATH} is missing required columns: {sorted(missing)}"
        )

    if "stratum_id" in proposals.columns:
        raise ValueError(
            "The Stage 01 proposal table must not already contain stratum_id."
        )

    proposal_sirens = normalize_siren(proposals[SIREN_COLUMN])
    requested_sirens = sorted(proposal_sirens.dropna().unique().tolist())

    stock_columns = [
        STOCK_SIREN_COLUMN,
        FIRST_NAME_COLUMN,
        LAST_NAME_COLUMN,
    ]
    if requested_sirens:
        stock = pd.read_parquet(
            STOCK_PATH,
            columns=stock_columns,
            filters=[(STOCK_SIREN_COLUMN, "in", requested_sirens)],
        )
    else:
        stock = pd.DataFrame(columns=stock_columns)

    stock[STOCK_SIREN_COLUMN] = normalize_siren(stock[STOCK_SIREN_COLUMN])

    duplicated = stock[STOCK_SIREN_COLUMN].duplicated(keep=False)
    if duplicated.any():
        sample = (
            stock.loc[duplicated, STOCK_SIREN_COLUMN]
            .value_counts()
            .head(20)
        )
        raise ValueError(
            "SIREN is not unique in the SIRENE legal-unit stock. Sample:\n"
            f"{sample.to_string()}"
        )

    person_by_siren = stock.set_index(STOCK_SIREN_COLUMN)[
        [FIRST_NAME_COLUMN, LAST_NAME_COLUMN]
    ]

    first_name = proposal_sirens.map(person_by_siren[FIRST_NAME_COLUMN])
    last_name = proposal_sirens.map(person_by_siren[LAST_NAME_COLUMN])

    denomination_is_missing = proposals[DENOMINATION_COLUMN].isna()
    last_name_is_filled = (
        last_name.notna()
        & last_name.astype("string").str.strip().ne("")
    )
    rows_to_update = denomination_is_missing & last_name_is_filled

    full_name = (
        first_name.astype("string")
        .fillna("")
        .str.strip()
        .str.cat(last_name.astype("string").str.strip(), sep=" ")
        .str.strip()
    )

    final_proposals = proposals.copy()
    final_proposals.loc[
        rows_to_update,
        DENOMINATION_COLUMN,
    ] = full_name.loc[rows_to_update]

    if len(final_proposals) != len(proposals):
        raise ValueError(
            "The denomination enrichment changed the number of proposal rows."
        )
    if final_proposals.columns.tolist() != proposals.columns.tolist():
        raise ValueError(
            "The denomination enrichment changed the proposal schema."
        )

    number_of_changes = int(rows_to_update.sum())
    log(
        "Denomination enrichment: "
        f"{len(final_proposals):,} proposal rows; "
        f"{number_of_changes:,} denomination(s) completed."
    )

    if write_output:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        export = final_proposals.copy()
        export.attrs = {}
        export.to_parquet(OUTPUT_PATH, index=False)
        log(f"Saved: {OUTPUT_PATH}")
    else:
        log("write_output is False; no file was written.")

    return {
        "proposals": final_proposals,
        "number_of_changes": number_of_changes,
        "output_path": OUTPUT_PATH if write_output else None,
    }


if __name__ == "__main__":
    run()