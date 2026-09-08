"""Complete missing SIRENE denominations in the EGE proposal table.

For proposed SIRET values whose legal-unit denomination is missing, this job looks
up the corresponding SIREN in the SIRENE legal-unit stock and uses the person's
first and last name when available. It publishes the denomination-enriched EGE
proposal table consumed by the FINESS-category enrichment job.
"""

from __future__ import annotations


def run() -> None:
    import pandas as pd

    from project_config import PATHS

    results_dir = PATHS.stage01_ege_proposals.parent
    input_path = results_dir / "ege_siret_proposals_01_base.parquet"
    output_path = (
        results_dir / "ege_siret_proposals_02_denomination_completed.parquet"
    )
    stock_path = PATHS.sirene_units_june

    siret_column = "siret_proposal"
    denomination_column = "siren__denominationUniteLegale"

    stock_siren_column = "siren"
    first_name_column = "prenom1UniteLegale"
    last_name_column = "nomUniteLegale"

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

    proposals = pd.read_parquet(input_path)

    required_columns = {siret_column, denomination_column}
    missing_columns = required_columns.difference(proposals.columns)
    if missing_columns:
        raise KeyError(
            f"{input_path} is missing required columns: {sorted(missing_columns)}"
        )

    # A proposed SIRET identifies its legal unit through its first nine digits.
    # Only these legal units are needed for the denomination completion.
    proposal_sirets = proposals[siret_column].astype("string").str.strip()
    proposal_sirens = normalize_siren(proposal_sirets.str[:9])
    requested_sirens = sorted(proposal_sirens.dropna().unique().tolist())

    stock_columns = [
        stock_siren_column,
        first_name_column,
        last_name_column,
    ]
    if requested_sirens:
        stock = pd.read_parquet(
            stock_path,
            columns=stock_columns,
            filters=[(stock_siren_column, "in", requested_sirens)],
        )
    else:
        stock = pd.DataFrame(columns=stock_columns)

    stock[stock_siren_column] = normalize_siren(stock[stock_siren_column])

    duplicated = stock[stock_siren_column].duplicated(keep=False)
    if duplicated.any():
        sample = (
            stock.loc[duplicated, stock_siren_column]
            .value_counts()
            .head(20)
        )
        raise ValueError(
            "SIREN is not unique in the SIRENE legal-unit stock. Sample:\n"
            f"{sample.to_string()}"
        )

    person_by_siren = stock.set_index(stock_siren_column)[
        [first_name_column, last_name_column]
    ]

    first_name = proposal_sirens.map(person_by_siren[first_name_column])
    last_name = proposal_sirens.map(person_by_siren[last_name_column])

    # Fill only genuine missing values. Literal strings such as "<NA>" remain
    # unchanged, matching the previous job behavior.
    denomination_is_missing = proposals[denomination_column].isna()
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
        denomination_column,
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

    final_proposals.to_parquet(output_path, index=False)

    print(
        "Denomination enrichment: "
        f"{len(final_proposals):,} proposal rows; "
        f"{len(requested_sirens):,} distinct SIREN requested; "
        f"{number_of_changes:,} denomination(s) completed. "
        f"Saved: {output_path}"
    )


if __name__ == "__main__":
    run()
