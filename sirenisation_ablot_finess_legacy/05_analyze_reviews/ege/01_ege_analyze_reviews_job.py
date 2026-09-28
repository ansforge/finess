"""Run the EGE review analysis and publish the two Stage 05 workbooks.

The EGE analysis reconstructs the realised two-stage EJ→EGE sampling design from
the confirmed EJ sample and pooled EGE frame before computing the per-stratum and
global review results.
"""

from __future__ import annotations


def run(
    *, write_outputs: bool = True, display_outputs: bool = True
) -> dict[str, object]:
    import sys

    import pandas as pd

    from project_config import PATHS, PROJECT_ROOT

    strata_module_dir = PROJECT_ROOT / "02_build_strata_plan"
    if str(strata_module_dir) not in sys.path:
        sys.path.insert(0, str(strata_module_dir))
    from stratum_codebook import load_stratum_codebook

    module_dir = PROJECT_ROOT / "05_analyze_reviews"
    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))

    import analyze_reviews as ar
    import review_global_summary as rgs

    log = print if display_outputs else lambda *_args, **_kwargs: None
    config = ar.EGE_SIRET_CONFIG
    ej_config = ar.EJ_SIREN_CONFIG

    all_confirmed_path = PATHS.stage04_ege_all_confirmed
    confirmed_path = (
        all_confirmed_path
        if all_confirmed_path.exists()
        else PATHS.stage04_ege_confirmed
    )
    plan_path = PATHS.stage02_ege_generated_plan
    proposal_path = PATHS.stage01_ege_proposals
    codebook_path = PATHS.stage02_stratum_codebook

    ej_all_confirmed_path = PATHS.stage04_ej_all_confirmed
    ej_confirmed_path = (
        ej_all_confirmed_path
        if ej_all_confirmed_path.exists()
        else PATHS.stage04_ej_confirmed
    )
    ej_plan_path = PATHS.stage02_ej_generated_plan
    pooled_ege_path = PATHS.stage02_ege_pooled_proposals

    enriched_plan_output = PATHS.stage05_ege_strata_analysis
    global_summary_output = PATHS.stage05_ege_summary

    workbook_note = (
        "Global EGE estimates are calibrated design-weighted "
        "estimates based on the realised two-stage EJ→EGE sampling design. See the "
        "accompanying methodology document for population definitions, "
        "weighting/calibration, fallback rules and scenario interpretation."
    )

    confirmed_decisions = ar.load_confirmed_decisions(
        confirmed_path,
        config=config,
    )
    proposals = ar.load_proposal_table(
        proposal_path,
        config=config,
    )
    strata_plan = ar.load_strata_plan(
        plan_path,
        config=config,
    )
    stratum_codebook = load_stratum_codebook(codebook_path)

    ej_confirmed_decisions = ar.load_confirmed_decisions(
        ej_confirmed_path,
        config=ej_config,
    )
    ej_strata_plan = ar.load_strata_plan(
        ej_plan_path,
        config=ej_config,
    )
    pooled_ege_proposals = pd.read_parquet(pooled_ege_path)

    pooled_frame_summary = ar.validate_ege_pooled_frame_against_plan(
        strata_plan,
        pooled_ege_proposals,
    )
    sampling_design = ar.build_ege_two_stage_sampling_design(
        ej_strata_plan,
        ej_confirmed_decisions,
        pooled_ege_proposals,
        ej_id_column="EJ",
        ege_id_column="EGE",
        stratum_id_column="stratum_id",
        ej_population_size_column="n_EJ",
    )

    per_stratum_analysis = ar.analyze_confirmed_decisions(
        confirmed_decisions,
        proposals,
        config=config,
    )
    enriched_strata_plan = ar.enrich_strata_plan(
        strata_plan,
        per_stratum_analysis,
        config=config,
        ege_sampling_design_df=sampling_design,
    )

    global_outputs = rgs.summarize_global_reviews(
        confirmed_decisions,
        proposals,
        enriched_strata_plan,
        config=config,
    )
    global_summary = global_outputs["global_summary_df"]
    accepted_strata_scenarios = global_outputs[
        "accepted_strata_scenarios_df"
    ]

    consistency = rgs.validate_global_analysis_consistency(
        proposals,
        strata_plan,
        global_summary,
        accepted_strata_scenarios,
        config=config,
    )

    output_paths = [enriched_plan_output, global_summary_output]
    if write_outputs:
        ar.export_dataframe(
            enriched_strata_plan,
            enriched_plan_output,
            sheet_name="analysis",
            supplementary_sheets={"stratum_codebook": stratum_codebook},
        )
        rgs.export_global_summary(
            global_outputs,
            global_summary_output,
            note=workbook_note,
        )

    decision_source = (
        "current review + supplementary decisions"
        if confirmed_path == all_confirmed_path
        else "current review"
    )
    log("EGE review analysis")
    log(f"- confirmed EGE: {len(confirmed_decisions):,} ({decision_source})")
    log(f"- analysed strata: {len(enriched_strata_plan):,}")
    log(f"- total EGE population: {consistency['known_population']:,.0f}")
    log(f"- pooled EGE: {pooled_frame_summary['pooled_ege_count']:,}")
    log(
        "- sampled EJ / pooled EGE in sampled strata: "
        f"{int(sampling_design['Sampled EJs'].sum()):,} / "
        f"{int(sampling_design['Pooled EGEs in sampled EJs'].sum()):,}"
    )
    log(
        "- estimated to match / to close: "
        f"{consistency['match_population']:,.2f} / "
        f"{consistency['close_population']:,.2f}"
    )
    if write_outputs:
        log("- saved:")
        for path in output_paths:
            log(f"  - {path}")
    else:
        log("- write_outputs is False; no files were written.")

    return {
        "confirmed_decisions": confirmed_decisions,
        "proposals": proposals,
        "strata_plan": strata_plan,
        "stratum_codebook": stratum_codebook,
        "ej_confirmed_decisions": ej_confirmed_decisions,
        "ej_strata_plan": ej_strata_plan,
        "pooled_ege_proposals": pooled_ege_proposals,
        "pooled_frame_summary": pooled_frame_summary,
        "sampling_design": sampling_design,
        "per_stratum_analysis": per_stratum_analysis,
        "enriched_strata_plan": enriched_strata_plan,
        "global_summary": global_summary,
        "accepted_strata_scenarios": accepted_strata_scenarios,
        "consistency_checks": consistency,
        "output_paths": output_paths if write_outputs else [],
    }


if __name__ == "__main__":
    run()
