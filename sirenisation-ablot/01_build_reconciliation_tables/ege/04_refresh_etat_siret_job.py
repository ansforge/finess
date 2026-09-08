"""Refresh proposed-SIRET administrative status and publish final EGE proposals.

This job updates ``etat_siret`` from the July SIRENE establishment stock while
preserving the existing value when no recognized current status is available. The
result is the final Stage 01 EGE proposal table consumed by Stage 02.
"""

from __future__ import annotations


def run() -> None:
    import pandas as pd

    from project_config import PATHS

    results_dir = PATHS.stage01_ege_proposals.parent
    input_path = results_dir / "ege_siret_proposals_03_libcategetab.parquet"
    output_path = PATHS.stage01_ege_proposals
    stock_path = PATHS.sirene_establishments_july

    siret_column = "siret_proposal"
    status_column = "etat_siret"

    stock_siret_column = "siret"
    stock_status_column = "etatAdministratifEtablissement"

    status_mapping = {
        "A": "",
        "C": "Cessé",
        "F": "Fermé",
    }

    proposals = pd.read_parquet(input_path)

    required_columns = {siret_column, status_column}
    missing_columns = required_columns.difference(proposals.columns)
    if missing_columns:
        raise KeyError(
            f"{input_path} is missing required columns: {sorted(missing_columns)}"
        )

    proposal_sirets = (
        proposals[siret_column]
        .astype("string")
        .str.strip()
        .replace({"": pd.NA, "N/A": pd.NA})
    )
    requested_sirets = sorted(proposal_sirets.dropna().unique().tolist())

    stock_columns = [stock_siret_column, stock_status_column]
    if requested_sirets:
        stock = pd.read_parquet(
            stock_path,
            columns=stock_columns,
            filters=[(stock_siret_column, "in", requested_sirets)],
        )
    else:
        stock = pd.DataFrame(columns=stock_columns)

    stock[stock_siret_column] = (
        stock[stock_siret_column]
        .astype("string")
        .str.strip()
    )

    duplicated = stock[stock_siret_column].duplicated(keep=False)
    if duplicated.any():
        sample = (
            stock.loc[duplicated, stock_siret_column]
            .value_counts()
            .head(20)
        )
        raise ValueError(
            "SIRET is not unique in the SIRENE establishment stock. Sample:\n"
            f"{sample.to_string()}"
        )

    status_by_siret = stock.set_index(stock_siret_column)[stock_status_column]
    mapped_status = proposal_sirets.map(status_by_siret).map(status_mapping)

    final_proposals = proposals.copy()
    updated_status = final_proposals[status_column].copy()

    # Preserve the existing value when the SIRET is absent from the July stock
    # or when its administrative status is not one of the recognized codes.
    matched_rows = mapped_status.notna()
    updated_status.loc[matched_rows] = mapped_status.loc[matched_rows]

    old_values = (
        final_proposals[status_column]
        .astype("string")
        .fillna("<NA>")
    )
    new_values = updated_status.astype("string").fillna("<NA>")
    number_of_changes = int((old_values != new_values).sum())

    final_proposals[status_column] = updated_status

    if len(final_proposals) != len(proposals):
        raise ValueError(
            "The administrative-status refresh changed the number of proposal rows."
        )
    if final_proposals.columns.tolist() != proposals.columns.tolist():
        raise ValueError(
            "The administrative-status refresh changed the proposal schema."
        )

    final_proposals.to_parquet(output_path, index=False)

    print(
        "Administrative-status refresh: "
        f"{len(final_proposals):,} proposal rows; "
        f"{len(requested_sirets):,} distinct SIRET requested; "
        f"{number_of_changes:,} status value(s) changed. "
        f"Saved: {output_path}"
    )


if __name__ == "__main__":
    run()
