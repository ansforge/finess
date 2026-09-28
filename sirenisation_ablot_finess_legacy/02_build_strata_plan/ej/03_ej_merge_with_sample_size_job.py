"""Apply manually entered EJ sample sizes to the reviewer-assigned strata plan.

This is the final EJ step of Stage 02. It validates the manual sample-size input,
adds ``sample_size`` to the reviewer-assigned plan, and publishes the plan consumed
by the review-export stage.
"""

from __future__ import annotations


def run(
    *, write_outputs: bool = True, display_outputs: bool = True
) -> dict[str, object]:
    import sys
    from pathlib import Path

    import pandas as pd

    from project_config import PATHS, PROJECT_ROOT

    module_dir = PROJECT_ROOT / "02_build_strata_plan"
    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))

    from reconciliation_strata_engine import merge_sample_sizes_into_review_plan

    log = print if display_outputs else lambda *_args, **_kwargs: None

    STRATA_PLAN_PATH = PATHS.stage02_ej_plan_with_reviewers
    SAMPLE_SIZE_PATH = PATHS.ej_sample_size_input
    OUTPUT_STRATA_PLAN_PATH = PATHS.stage02_ej_review_plan
    OUTPUT_REVIEWER_STATISTICS_PATH = (
        OUTPUT_STRATA_PLAN_PATH.parent
        / "ej_reviewer_statistics_with_sample_size.xlsx"
    )

    strata_plan = pd.read_excel(
        STRATA_PLAN_PATH,
        sheet_name=0,
        dtype="string",
    )
    sample_size_input = pd.read_excel(
        SAMPLE_SIZE_PATH,
        sheet_name=0,
        dtype="string",
    )

    result = merge_sample_sizes_into_review_plan(
        strata_plan,
        sample_size_input,
        population_column="n_EJ",
    )

    final_plan = result.strata_plan
    reviewer_statistics = result.reviewer_statistics

    log("EJ final review plan")
    log(f"- strata: {len(final_plan):,}")
    log(f"- EJ population represented: {int(final_plan['n_EJ'].sum()):,}")
    log(f"- planned EJ reviews: {int(final_plan['sample_size'].sum()):,}")
    log(f"- reviewers: {final_plan['reviewer'].nunique(dropna=True):,}")

    output_paths: dict[str, Path] = {}
    if write_outputs:
        OUTPUT_STRATA_PLAN_PATH.parent.mkdir(parents=True, exist_ok=True)

        export_plan = final_plan.copy()
        export_statistics = reviewer_statistics.copy()
        export_plan.attrs = {}
        export_statistics.attrs = {}

        export_plan.to_excel(
            OUTPUT_STRATA_PLAN_PATH,
            sheet_name="strata_plan",
            index=False,
            engine="openpyxl",
        )
        export_statistics.to_excel(
            OUTPUT_REVIEWER_STATISTICS_PATH,
            sheet_name="reviewer_statistics",
            index=False,
            engine="openpyxl",
        )

        output_paths = {
            "strata_plan_with_sample_size": OUTPUT_STRATA_PLAN_PATH,
            "reviewer_statistics_with_sample_size": (
                OUTPUT_REVIEWER_STATISTICS_PATH
            ),
        }

        log("Saved final EJ review-plan outputs:")
        for path in output_paths.values():
            log(f"- {path}")
    else:
        log("write_outputs is False; no files were written.")

    return {
        "strata_plan": strata_plan,
        "sample_size_input": result.sample_size_input,
        "strata_plan_with_sample_size": final_plan,
        "reviewer_statistics": reviewer_statistics,
        "output_paths": output_paths,
    }


if __name__ == "__main__":
    run()
