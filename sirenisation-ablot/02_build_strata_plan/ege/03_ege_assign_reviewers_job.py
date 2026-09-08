"""Assign reviewers to the EGE strata plan.

Within Stage 02, the pooled EGE frame is built first, then
``02_ege_build_strata_plan_job.py`` builds ``ege_strata_plan.xlsx``.
This job assigns one reviewer to each stratum; the following job adds the
manually entered sample size.

Reviewer assignment supports the two strategies provided by the shared engine:
- ``"mapping"``: load an explicit stratum-to-reviewer mapping;
- ``"round_robin"``: assign reviewers deterministically with a seeded round-robin.
"""

from __future__ import annotations


def run(
    *, write_outputs: bool = True, display_outputs: bool = True
) -> dict[str, object]:
    import sys
    from pathlib import Path

    import pandas as pd

    from project_config import PATHS, PROJECT_ROOT

    log = print if display_outputs else lambda *_args, **_kwargs: None

    module_dir = PROJECT_ROOT / "02_build_strata_plan"
    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))

    from reconciliation_strata_engine import (
        ENTITY_COUNT,
        ReconciliationNames,
        assign_reviewers_round_robin,
        load_stratum_reviewer_mapping,
        load_table,
        to_user_columns,
    )


    # -----------------------------------------------------------------------
    # Reconciliation profile
    # -----------------------------------------------------------------------

    NAMES = ReconciliationNames.ege_siret()
    USER_ENTITY_COUNT_COLUMN = NAMES.user_entity_count_column
    POOLED_COUNT_COLUMN = "n_EGE_pooled"

    # -----------------------------------------------------------------------
    # Paths
    # -----------------------------------------------------------------------

    INPUT_PLAN_PATH = PATHS.stage02_ege_generated_plan

    OUTPUT_PLAN_PATH = PATHS.stage02_ege_plan_with_reviewers
    OUTPUT_DIR = OUTPUT_PLAN_PATH.parent
    REVIEWER_STATISTICS_OUTPUT_PATH = (
        OUTPUT_DIR / "ege_reviewer_statistics.xlsx"
    )

    # -----------------------------------------------------------------------
    # Reviewer assignment
    # -----------------------------------------------------------------------

    # Choose: "mapping" or "round_robin".
    REVIEWER_ASSIGNMENT_MODE = "mapping"

    # Used when REVIEWER_ASSIGNMENT_MODE == "mapping".
    #
    # This file is independent from the sample-size input used by the next
    # Stage 02 job. It only needs:
    #   - stratum_id
    #   - reviewer
    STRATUM_REVIEWER_MAPPING_PATH = PATHS.ege_stratum_reviewer_mapping
    STRATUM_REVIEWER_MAPPING_SHEET = 0
    STRATUM_REVIEWER_MAPPING_STRATUM_COLUMN = "stratum_id"
    STRATUM_REVIEWER_MAPPING_REVIEWER_COLUMN = "reviewer"

    # Used when REVIEWER_ASSIGNMENT_MODE == "round_robin".
    REVIEWERS = [
        "Reviewer 1",
        "Reviewer 2",
    ]
    REVIEWER_ASSIGNMENT_SEED = "ege-reviewer-2026-07"

    ERROR_SAMPLE_ROWS = 20

    # -----------------------------------------------------------------------
    # Load and normalize the strata plan
    # -----------------------------------------------------------------------

    strata_plan = load_table(INPUT_PLAN_PATH)

    required_columns = {
        "stratum_id",
        USER_ENTITY_COUNT_COLUMN,
        POOLED_COUNT_COLUMN,
    }
    missing_columns = sorted(required_columns - set(strata_plan.columns))
    if missing_columns:
        raise KeyError(
            f"Missing required column(s) in {INPUT_PLAN_PATH}: {missing_columns}"
        )

    reviewer_plan_base = strata_plan.rename(
        columns={USER_ENTITY_COUNT_COLUMN: ENTITY_COUNT}
    ).copy()

    entity_counts = pd.to_numeric(
        reviewer_plan_base[ENTITY_COUNT],
        errors="coerce",
    )
    if entity_counts.isna().any():
        bad_values = (
            reviewer_plan_base.loc[
                entity_counts.isna(),
                ["stratum_id", ENTITY_COUNT],
            ]
            .head(10)
            .to_dict("records")
        )
        raise ValueError(
            f"{USER_ENTITY_COUNT_COLUMN} must contain integer population counts. "
            f"Invalid values: {bad_values}"
        )

    invalid_counts = (entity_counts < 0) | (entity_counts % 1 != 0)
    if invalid_counts.any():
        bad_values = (
            reviewer_plan_base.loc[
                invalid_counts,
                ["stratum_id", ENTITY_COUNT],
            ]
            .head(10)
            .to_dict("records")
        )
        raise ValueError(
            f"{USER_ENTITY_COUNT_COLUMN} must contain non-negative integers. "
            f"Invalid values: {bad_values}"
        )

    reviewer_plan_base[ENTITY_COUNT] = entity_counts.astype("int64")

    pooled_counts = pd.to_numeric(
        reviewer_plan_base[POOLED_COUNT_COLUMN],
        errors="coerce",
    )
    invalid_pooled_counts = (
        pooled_counts.isna()
        | pooled_counts.lt(0)
        | pooled_counts.mod(1).ne(0)
        | pooled_counts.gt(reviewer_plan_base[ENTITY_COUNT])
    )
    if invalid_pooled_counts.any():
        bad_values = (
            reviewer_plan_base.loc[
                invalid_pooled_counts,
                ["stratum_id", ENTITY_COUNT, POOLED_COUNT_COLUMN],
            ]
            .head(10)
            .to_dict("records")
        )
        raise ValueError(
            f"{POOLED_COUNT_COLUMN} must contain non-negative integer counts "
            "not exceeding the total EGE population. "
            f"Invalid values: {bad_values}"
        )

    reviewer_plan_base[POOLED_COUNT_COLUMN] = pooled_counts.astype("int64")


    # -----------------------------------------------------------------------
    # Assign reviewers
    # -----------------------------------------------------------------------

    if REVIEWER_ASSIGNMENT_MODE == "round_robin":
        reviewer_result = assign_reviewers_round_robin(
            reviewer_plan_base,
            REVIEWERS,
            seed=REVIEWER_ASSIGNMENT_SEED,
        )

    elif REVIEWER_ASSIGNMENT_MODE == "mapping":
        stratum_reviewer_mapping = load_table(
            STRATUM_REVIEWER_MAPPING_PATH,
            sheet_name=STRATUM_REVIEWER_MAPPING_SHEET,
        )

        reviewer_result = load_stratum_reviewer_mapping(
            reviewer_plan_base,
            stratum_reviewer_mapping,
            mapping_stratum_column=STRATUM_REVIEWER_MAPPING_STRATUM_COLUMN,
            mapping_reviewer_column=STRATUM_REVIEWER_MAPPING_REVIEWER_COLUMN,
        )

    else:
        raise ValueError(
            "REVIEWER_ASSIGNMENT_MODE must be 'mapping' or 'round_robin'."
        )

    strata_plan_with_reviewers = reviewer_result.strata_plan
    reviewer_statistics = reviewer_result.reviewer_statistics
    missing_reviewer_assignments = reviewer_result.missing_reviewer_assignments

    if not missing_reviewer_assignments.empty:
        sample = to_user_columns(
            missing_reviewer_assignments,
            NAMES,
        ).head(ERROR_SAMPLE_ROWS)
        raise ValueError(
            "At least one stratum has no reviewer. Complete the reviewer assignment "
            f"before continuing Stage 02. Sample:\n{sample.to_string(index=False)}"
        )

    strata_plan_view = to_user_columns(
        strata_plan_with_reviewers,
        NAMES,
    )
    reviewer_statistics_view = reviewer_statistics.rename(
        columns={ENTITY_COUNT: USER_ENTITY_COUNT_COLUMN}
    )

    log("EGE reviewer assignment")
    log(f"- mode: {REVIEWER_ASSIGNMENT_MODE}")
    log(f"- strata: {len(strata_plan_view):,}")
    log(f"- reviewers: {reviewer_statistics_view['reviewer'].nunique(dropna=True):,}")
    log(
        f"- total EGE represented: "
        f"{int(reviewer_statistics_view[USER_ENTITY_COUNT_COLUMN].sum()):,}"
    )
    log(
        f"- pooled EGE available: "
        f"{int(strata_plan_view[POOLED_COUNT_COLUMN].sum()):,}"
    )

    # -----------------------------------------------------------------------
    # Export
    # -----------------------------------------------------------------------

    output_paths: dict[str, Path] = {}
    if write_outputs:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        strata_plan_view = strata_plan_view.copy()
        reviewer_statistics_view = reviewer_statistics_view.copy()
        strata_plan_view.attrs = {}
        reviewer_statistics_view.attrs = {}

        strata_plan_view.to_excel(
            OUTPUT_PLAN_PATH,
            sheet_name="strata_plan",
            index=False,
            engine="openpyxl",
        )
        reviewer_statistics_view.to_excel(
            REVIEWER_STATISTICS_OUTPUT_PATH,
            sheet_name="reviewer_statistics",
            index=False,
            engine="openpyxl",
        )

        output_paths = {
            "strata_plan_with_reviewers": OUTPUT_PLAN_PATH,
            "reviewer_statistics": REVIEWER_STATISTICS_OUTPUT_PATH,
        }

        log("Saved reviewer-assignment outputs:")
        for path in output_paths.values():
            log(f"- {path}")
    else:
        log("write_outputs is False; no files were written.")

    return {
        "input_strata_plan": strata_plan,
        "strata_plan_with_reviewers": strata_plan_view,
        "reviewer_statistics": reviewer_statistics_view,
        "missing_reviewer_assignments": to_user_columns(
            missing_reviewer_assignments,
            NAMES,
        ),
        "output_paths": output_paths,
    }


if __name__ == "__main__":
    run()
