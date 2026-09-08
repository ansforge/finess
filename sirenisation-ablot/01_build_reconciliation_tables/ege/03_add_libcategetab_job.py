"""Add the FINESS establishment category to the EGE proposal table.

This job joins ``libcategetab`` from the prepared FINESS EGE dataset to every
proposal row and publishes the category-enriched EGE proposal table consumed by
the final administrative-status refresh job of Stage 01.
"""

from __future__ import annotations


def run() -> None:
    import pandas as pd

    from project_config import PATHS

    # Input/output paths
    RESULTS_DIR = PATHS.stage01_ege_proposals.parent
    INPUT_PATH = RESULTS_DIR / "ege_siret_proposals_02_denomination_completed.parquet"
    OUTPUT_PATH = RESULTS_DIR / "ege_siret_proposals_03_libcategetab.parquet"

    INPUT_ESTABLISHMENTS = PATHS.finess_ege_prepared


    # Load the proposal data
    proposals = pd.read_parquet(INPUT_PATH)

    # Load only the required columns from the establishment dataset
    establishments = pd.read_parquet(
        INPUT_ESTABLISHMENTS,
        columns=["nofinesset", "libcategetab"],
    )

    # Create normalized join keys without modifying the original EGE column
    proposals["_join_key"] = proposals["EGE"].astype("string")
    establishments["_join_key"] = (
        establishments["nofinesset"].astype("string").str.strip()
    )

    # Confirm that the lookup key remains unique
    if establishments["_join_key"].duplicated().any():
        duplicates = establishments.loc[
            establishments["_join_key"].duplicated(keep=False),
            "nofinesset",
        ].unique()

        raise ValueError(
            "nofinesset is not unique after key normalization. "
            f"Example duplicate values: {duplicates[:10].tolist()}"
        )

    # Add libcategetab to every matching EGE row
    result = proposals.merge(
        establishments[["_join_key", "libcategetab"]],
        on="_join_key",
        how="left",
        validate="many_to_one",
    )

    result = (
        result
        .drop(columns="_join_key")
        .rename(columns={"libcategetab": "EGE__libcategetab"})
    )


    # Export to Parquet
    result.to_parquet(
        OUTPUT_PATH,
        index=False,
    )

    missing_category_count = int(result["EGE__libcategetab"].isna().sum())
    print(
        "FINESS category enrichment: "
        f"{len(result):,} proposal rows; "
        f"{missing_category_count:,} row(s) without libcategetab. "
        f"Saved: {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    run()
