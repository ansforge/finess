"""Consolidate EGE review workbooks into current confirmed decisions.

This job validates the completed review batch against the proposal frame, publishes
the realised reviewed sample and one confirmed decision per reviewed EGE, then
reports non-blocking deviations from the final review plan.
"""

from __future__ import annotations


def run(*, write_outputs: bool = True) -> dict[str, object]:
    import sys

    from project_config import PATHS, PROJECT_ROOT

    module_dir = PROJECT_ROOT / "04_merge_reviews"
    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))

    import merge_reviews as mrp

    config = mrp.EGE_SIRET_CONFIG
    review_root = PATHS.ege_review_root
    plan_path = PATHS.stage02_ege_review_plan
    proposal_path = PATHS.stage02_ege_pooled_proposals

    confirmed_output = PATHS.stage04_ege_confirmed
    output_dir = confirmed_output.parent
    reviewed_sample_parquet = output_dir / "ege_reviewed_sample.parquet"
    reviewed_sample_excel = output_dir / "ege_reviewed_sample.xlsx"
    confirmed_excel = confirmed_output.with_suffix(".xlsx")

    all_confirmed_output = PATHS.stage04_ege_all_confirmed
    all_confirmed_excel = all_confirmed_output.with_suffix(".xlsx")

    review_rows, loaded_files = mrp.load_stratum_files(
        review_root,
        config=config,
    )
    proposals = mrp.load_proposal_table(proposal_path, config=config)
    mrp.validate_stratum_entities_against_proposals(
        review_rows,
        proposals,
        config=config,
        source=str(proposal_path),
    )
    strata_plan = mrp.load_strata_plan(plan_path, config=config)

    reviewed_sample = mrp.filter_reviewed_cases(review_rows, config=config)
    confirmed_decisions = mrp.build_confirmed_database(review_rows, config=config)

    reviewed_entity_count = reviewed_sample["EGE"].nunique(dropna=True)

    output_paths = [
        reviewed_sample_parquet,
        reviewed_sample_excel,
        confirmed_output,
        confirmed_excel,
    ]
    if write_outputs:
        # A fresh direct consolidation invalidates any previous optional combination.
        for stale_output in (all_confirmed_output, all_confirmed_excel):
            if stale_output.exists():
                stale_output.unlink()

        mrp.export_dataframe(reviewed_sample, reviewed_sample_parquet)
        mrp.export_dataframe(reviewed_sample, reviewed_sample_excel)
        mrp.export_dataframe(confirmed_decisions, confirmed_output)
        mrp.export_dataframe(confirmed_decisions, confirmed_excel)

    print("EGE review consolidation")
    print(f"- review workbooks: {len(loaded_files):,}")
    print(f"- reviewed EGE: {reviewed_entity_count:,}")
    print(f"- confirmed decisions: {len(confirmed_decisions):,}")
    print(f"- planned strata: {len(strata_plan):,}")
    if write_outputs:
        print("- saved:")
        for path in output_paths:
            print(f"  - {path}")
    else:
        print("- write_outputs is False; no files were written.")

    # Keep design notices last so they remain visible in interactive runs.
    missing_strata = mrp.report_missing_strata(
        plan_df=strata_plan,
        stratum_df=review_rows,
        config=config,
    )
    review_design = mrp.report_review_design_deviations(
        plan_df=strata_plan,
        stratum_df=review_rows,
        config=config,
    )
    if (
        not missing_strata
        and not review_design["review_shortfalls"]
        and not review_design["review_extensions"]
        and not review_design["internal_review_gaps"]
    ):
        print("Review design checks: no deviations found.")

    return {
        "review_rows": review_rows,
        "loaded_files": loaded_files,
        "proposals": proposals,
        "strata_plan": strata_plan,
        "missing_strata": missing_strata,
        **review_design,
        "reviewed_sample": reviewed_sample,
        "confirmed_decisions": confirmed_decisions,
        "output_paths": output_paths if write_outputs else [],
    }


if __name__ == "__main__":
    run()
