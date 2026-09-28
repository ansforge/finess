"""Assign reviewers to the EJ strata plan.

This job is the second step of Stage 02:
1. ``01_ej_build_strata_plan_job.py`` builds ``ej_strata_plan.xlsx``.
2. This job assigns one reviewer to each stratum.
3. ``03_ej_merge_with_sample_size_job.py`` adds the manually entered sample size.

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

    NAMES = ReconciliationNames.ej_siren()
    USER_ENTITY_COUNT_COLUMN = NAMES.user_entity_count_column

    # -----------------------------------------------------------------------
    # Paths
    # -----------------------------------------------------------------------

    INPUT_PLAN_PATH = PATHS.stage02_ej_generated_plan

    OUTPUT_PLAN_PATH = PATHS.stage02_ej_plan_with_reviewers
    OUTPUT_DIR = OUTPUT_PLAN_PATH.parent
    REVIEWER_STATISTICS_OUTPUT_PATH = OUTPUT_DIR / "ej_reviewer_statistics.xlsx"

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
    STRATUM_REVIEWER_MAPPING_PATH = PATHS.ej_stratum_reviewer_mapping
    STRATUM_REVIEWER_MAPPING_SHEET = 0
    STRATUM_REVIEWER_MAPPING_STRATUM_COLUMN = "stratum_id"
    STRATUM_REVIEWER_MAPPING_REVIEWER_COLUMN = "reviewer"

    # Used when REVIEWER_ASSIGNMENT_MODE == "round_robin".
    REVIEWERS = [
        "Reviewer 1",
        "Reviewer 2",
    ]
    REVIEWER_ASSIGNMENT_SEED = "ej-stratum-2026-07"

    ERROR_SAMPLE_ROWS = 20

    # -----------------------------------------------------------------------
    # Load and normalize the strata plan
    # -----------------------------------------------------------------------

    strata_plan = load_table(INPUT_PLAN_PATH)

    required_columns = {"stratum_id", USER_ENTITY_COUNT_COLUMN}
    missing_columns = sorted(required_columns - set(strata_plan.columns))
    if missing_columns:
        raise KeyError(
            f"Missing required column(s) in {INPUT_PLAN_PATH}: {missing_columns}"
        )

    # The shared engine works internally with ``n_entity``. Stage 02.1 exports
    # user-facing ``n_EJ``, so normalize that single column at the boundary.
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
    if (entity_counts < 0).any() or (entity_counts % 1 != 0).any():
        bad_values = (
            reviewer_plan_base.loc[
                (entity_counts < 0) | (entity_counts % 1 != 0),
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

    reviewer_statistics_view = reviewer_statistics.rename(
        columns={ENTITY_COUNT: USER_ENTITY_COUNT_COLUMN}
    )

    log("EJ reviewer assignment")
    log(f"- mode: {REVIEWER_ASSIGNMENT_MODE}")
    log(f"- strata: {len(strata_plan_with_reviewers):,}")
    log(f"- reviewers: {reviewer_statistics_view['reviewer'].nunique(dropna=True):,}")
    log(
        f"- EJ covered: "
        f"{int(reviewer_statistics_view[USER_ENTITY_COUNT_COLUMN].sum()):,}"
    )

    # -----------------------------------------------------------------------
    # Export
    # -----------------------------------------------------------------------

    output_paths: dict[str, Path] = {}
    if write_outputs:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        exported_plan = to_user_columns(
            strata_plan_with_reviewers,
            NAMES,
        )
        exported_plan.attrs = {}
        reviewer_statistics_view = reviewer_statistics_view.copy()
        reviewer_statistics_view.attrs = {}

        exported_plan.to_excel(
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
        "strata_plan_with_reviewers": to_user_columns(
            strata_plan_with_reviewers,
            NAMES,
        ),
        "reviewer_statistics": reviewer_statistics_view,
        "missing_reviewer_assignments": to_user_columns(
            missing_reviewer_assignments,
            NAMES,
        ),
        "output_paths": output_paths,
    }


if __name__ == "__main__":
    run()
