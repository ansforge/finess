"""Build the Stage 02 EGE strata plan from strata inherited from parent EJs.

This job validates the inherited ``stratum_id`` attached to each EGE, checks
that the pooled EGE frame is consistent with those assignments, counts the
total and pooled EGE in each stratum, and publishes the EGE strata assignments
and strata plan used by the reviewer-assignment and sample-size jobs.
"""

from __future__ import annotations


def run(
    *, write_outputs: bool = True, display_outputs: bool = True
) -> dict[str, object]:
    import sys
    from pathlib import Path

    import pandas as pd

    from project_config import PATHS, PROJECT_ROOT

    MODULE_DIR = PROJECT_ROOT / "02_build_strata_plan"
    if str(MODULE_DIR) not in sys.path:
        sys.path.insert(0, str(MODULE_DIR))

    from reconciliation_strata_engine import (
        ENTITY_COUNT,
        ReconciliationNames,
        build_plan_from_existing_strata,
        load_table,
        to_user_columns,
    )

    log = print if display_outputs else lambda *_args, **_kwargs: None

    # ---------------------------------------------------------------------------
    # EGE strata inherited from the parent EJ
    # ---------------------------------------------------------------------------

    NAMES = ReconciliationNames.ege_siret()
    ENTITY_COLUMN = NAMES.entity_id_column
    STRATUM_COLUMN = "stratum_id"
    POOLED_COUNT_COLUMN = "n_EGE_pooled"

    # Stage 01 EGE inherits the parent EJ stratum_id into the enriched EGE
    # consistency table. Stage 02 keeps that stratification and combines the
    # total EGE population with the pooled EGE frame built immediately
    # before this job.
    INPUT_PATH = PATHS.stage01_ege_consistency_enriched
    POOLED_PROPOSALS_PATH = PATHS.stage02_ege_pooled_proposals

    # ---------------------------------------------------------------------------
    # Outputs
    # ---------------------------------------------------------------------------

    STRATA_PLAN_OUTPUT = PATHS.stage02_ege_generated_plan
    OUTPUT_DIR = STRATA_PLAN_OUTPUT.parent
    ENTITY_ASSIGNMENTS_OUTPUT = OUTPUT_DIR / "ege_strata_assignments.parquet"

    ERROR_SAMPLE_ROWS = 20

    input_table = load_table(INPUT_PATH)

    required_columns = {ENTITY_COLUMN, STRATUM_COLUMN}
    missing_columns = sorted(required_columns - set(input_table.columns))
    if missing_columns:
        raise KeyError(
            f"Missing required column(s) in {INPUT_PATH}: {missing_columns}"
        )

    if input_table[ENTITY_COLUMN].isna().any():
        raise ValueError(f"{INPUT_PATH} contains missing {ENTITY_COLUMN} values.")

    if input_table[ENTITY_COLUMN].duplicated().any():
        duplicated_entities = (
            input_table.loc[
                input_table[ENTITY_COLUMN].duplicated(keep=False),
                ENTITY_COLUMN,
            ]
            .astype("string")
            .drop_duplicates()
            .head(20)
            .tolist()
        )
        raise ValueError(
            f"{INPUT_PATH} must contain one row per {ENTITY_COLUMN}. "
            f"Duplicate examples: {duplicated_entities}"
        )

    stratum_values = (
        input_table[STRATUM_COLUMN]
        .astype("string")
        .str.strip()
        .replace("", pd.NA)
    )
    if stratum_values.isna().any():
        missing_entities = (
            input_table.loc[stratum_values.isna(), ENTITY_COLUMN]
            .astype("string")
            .head(20)
            .tolist()
        )
        raise ValueError(
            "Every EGE must inherit a stratum_id from its parent EJ before "
            f"Stage 02. Missing examples: {missing_entities}"
        )

    input_table = input_table.copy()
    input_table[ENTITY_COLUMN] = (
        input_table[ENTITY_COLUMN]
        .astype("string")
        .str.strip()
        .replace("", pd.NA)
    )
    input_table[STRATUM_COLUMN] = stratum_values

    pooled_proposals = load_table(POOLED_PROPOSALS_PATH)
    pooled_required_columns = {ENTITY_COLUMN, STRATUM_COLUMN}
    missing_pooled_columns = sorted(
        pooled_required_columns - set(pooled_proposals.columns)
    )
    if missing_pooled_columns:
        raise KeyError(
            f"Missing required column(s) in {POOLED_PROPOSALS_PATH}: "
            f"{missing_pooled_columns}"
        )

    pooled_entity_strata = pooled_proposals[
        [ENTITY_COLUMN, STRATUM_COLUMN]
    ].copy()
    pooled_entity_strata[ENTITY_COLUMN] = (
        pooled_entity_strata[ENTITY_COLUMN]
        .astype("string")
        .str.strip()
        .replace("", pd.NA)
    )
    pooled_entity_strata[STRATUM_COLUMN] = (
        pooled_entity_strata[STRATUM_COLUMN]
        .astype("string")
        .str.strip()
        .replace("", pd.NA)
    )

    if pooled_entity_strata[[ENTITY_COLUMN, STRATUM_COLUMN]].isna().any().any():
        raise ValueError(
            f"{POOLED_PROPOSALS_PATH} contains missing {ENTITY_COLUMN} or "
            f"{STRATUM_COLUMN} values."
        )

    pooled_strata_per_entity = (
        pooled_entity_strata.groupby(ENTITY_COLUMN, dropna=False)[STRATUM_COLUMN]
        .nunique(dropna=False)
    )
    inconsistent_pooled_entities = pooled_strata_per_entity[
        pooled_strata_per_entity.ne(1)
    ]
    if not inconsistent_pooled_entities.empty:
        raise ValueError(
            "Every pooled EGE must belong to exactly one inherited stratum. "
            f"Examples: {inconsistent_pooled_entities.head(20).index.tolist()}"
        )

    pooled_entity_strata = pooled_entity_strata.drop_duplicates(
        subset=[ENTITY_COLUMN, STRATUM_COLUMN]
    )

    full_entity_strata = input_table[
        [ENTITY_COLUMN, STRATUM_COLUMN]
    ].drop_duplicates()
    pooled_check = pooled_entity_strata.merge(
        full_entity_strata,
        on=ENTITY_COLUMN,
        how="left",
        suffixes=("_pooled", "_full"),
        validate="one_to_one",
        indicator=True,
    )

    unknown_pooled_entities = pooled_check.loc[
        pooled_check["_merge"].ne("both"),
        ENTITY_COLUMN,
    ]
    if not unknown_pooled_entities.empty:
        raise ValueError(
            f"{POOLED_PROPOSALS_PATH} contains EGE absent from {INPUT_PATH}. "
            f"Examples: {unknown_pooled_entities.head(20).tolist()}"
        )

    mismatched_strata = pooled_check[
        pooled_check[f"{STRATUM_COLUMN}_pooled"].ne(
            pooled_check[f"{STRATUM_COLUMN}_full"]
        )
    ]
    if not mismatched_strata.empty:
        sample = mismatched_strata[
            [
                ENTITY_COLUMN,
                f"{STRATUM_COLUMN}_pooled",
                f"{STRATUM_COLUMN}_full",
            ]
        ].head(20)
        raise ValueError(
            "Pooled EGE strata must match the strata inherited in the Stage 01 "
            f"EGE consistency table. Sample:\n{sample.to_string(index=False)}"
        )

    strata_result = build_plan_from_existing_strata(
        input_table,
        names=NAMES,
        stratum_column=STRATUM_COLUMN,
    )

    entity_assignments = strata_result.entity_assignments
    strata_plan = strata_result.strata_plan

    pooled_counts = (
        pooled_entity_strata.groupby(STRATUM_COLUMN, dropna=False)
        .agg(**{POOLED_COUNT_COLUMN: (ENTITY_COLUMN, "nunique")})
        .reset_index()
    )
    strata_plan = strata_plan.merge(
        pooled_counts,
        on=STRATUM_COLUMN,
        how="left",
        validate="one_to_one",
    )
    strata_plan[POOLED_COUNT_COLUMN] = (
        strata_plan[POOLED_COUNT_COLUMN].fillna(0).astype("int64")
    )

    missing_entity_assignments = strata_result.missing_entity_assignments

    if not missing_entity_assignments.empty:
        sample = to_user_columns(
            missing_entity_assignments,
            NAMES,
        ).head(ERROR_SAMPLE_ROWS)
        raise ValueError(
            "At least one EGE has no inherited stratum_id; Stage 02 cannot "
            f"continue. Sample:\n{sample.to_string(index=False)}"
        )

    strata_with_pooled_ege = int(strata_plan[POOLED_COUNT_COLUMN].gt(0).sum())
    log("EGE strata plan")
    log(f"- total EGE: {len(entity_assignments):,}")
    log(f"- pooled EGE: {len(pooled_entity_strata):,}")
    log(f"- inherited strata: {len(strata_plan):,}")
    log(f"- strata with pooled EGE: {strata_with_pooled_ege:,}")

    stratum_statistics_columns = [
        "stratum_id",
        *strata_result.stratification_variables,
        ENTITY_COUNT,
        POOLED_COUNT_COLUMN,
    ]

    stratum_statistics = strata_plan.loc[
        :,
        stratum_statistics_columns,
    ].copy()

    output_paths: dict[str, Path] = {}
    if write_outputs:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        exported_assignments = to_user_columns(entity_assignments, NAMES)
        exported_plan = to_user_columns(strata_plan, NAMES)

        exported_assignments.attrs = {}
        exported_plan.attrs = {}

        exported_assignments.to_parquet(
            ENTITY_ASSIGNMENTS_OUTPUT,
            index=False,
        )
        exported_plan.to_excel(
            STRATA_PLAN_OUTPUT,
            sheet_name="strata_plan",
            index=False,
            engine="openpyxl",
        )

        output_paths = {
            "strata_plan": STRATA_PLAN_OUTPUT,
            "entity_assignments": ENTITY_ASSIGNMENTS_OUTPUT,
        }

        log("Saved EGE strata-plan outputs:")
        for path in output_paths.values():
            log(f"- {path}")
    else:
        log("write_outputs is False; no files were written.")

    return {
        "input": input_table,
        "entity_assignments": entity_assignments,
        "strata_plan": strata_plan,
        "stratum_statistics": stratum_statistics,
        "missing_entity_assignments": missing_entity_assignments,
        "output_paths": output_paths,
    }



if __name__ == "__main__":
    run()
