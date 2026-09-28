"""Assign EJ to strata and build the Stage 02 EJ strata plan and codebook.

In ``coding`` mode, the configured categorical domains define both EJ stratum
IDs and the complete theoretical codebook. In ``mapping`` mode, assignments and
the complete codebook come from the supplied mapping. The resulting strata are
then attached to the Stage 01 consistency and proposal tables.
"""

from __future__ import annotations


def run(
    *, write_outputs: bool = True, display_outputs: bool = True
) -> dict[str, object]:
    import sys

    import pandas as pd

    from project_config import PATHS, PROJECT_ROOT

    module_dir = PROJECT_ROOT / "02_build_strata_plan"
    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))

    from reconciliation_strata_engine import (
        ENTITY_COUNT,
        ReconciliationNames,
        attach_stratification,
        build_strata_from_variables,
        load_entity_strata_mapping,
        load_table,
        to_user_columns,
    )
    from stratum_codebook import (
        export_stratum_codebook,
        validate_stratum_codebook,
    )

    log = print if display_outputs else lambda *_args, **_kwargs: None

    names = ReconciliationNames.ej_siren(entity_pad_width=9)
    entity_column = names.entity_id_column

    enriched_input = PATHS.stage01_ej_consistency_enriched
    proposals_input = PATHS.stage01_ej_proposals

    output_dir = PATHS.stage02_ej_generated_plan.parent
    stratified_enriched_output = (
        output_dir / "ej_siren_consistency_enriched_stratified.parquet"
    )
    stratified_proposals_output = PATHS.stage02_ej_stratified_proposals
    strata_plan_output = PATHS.stage02_ej_generated_plan
    entity_assignments_output = output_dir / "ej_strata_assignments.parquet"
    codebook_output = PATHS.stage02_stratum_codebook

    # Change only this setting to switch between the two supported mechanisms.
    stratification_mode = "coding"

    # These variables and domains define the current EJ coding scheme. The
    # generic engine uses whatever variables/domains are supplied here; the
    # codebook module itself has no knowledge of this definition.
    stratification_variables = [
        "coherence_EJ_ANS",
        "statut_EJ_ANS",
        "is_initial_siren_ANS",
        "statut_validation_Adrien",
        "datasets_consistency",
        "secteur_EJ",
    ]
    stratification_orders = {
        "coherence_EJ_ANS": ["<NA>", "EJ seul", "Incohérent", "Cohérent"],
        "statut_EJ_ANS": ["<NA>", "VALIDE", "VALIDE_FORT"],
        "is_initial_siren_ANS": ["<NA>", "False", "True"],
        "statut_validation_Adrien": [
            "0 proposition",
            "1 proposition",
            "2+ propositions",
        ],
        "datasets_consistency": [
            "Total inconsistency",
            "Partial consistency",
            "Total consistency",
        ],
        "secteur_EJ": ["autre", "ehpad_hopitaux", "scm_sel"],
    }

    mapping_path = PATHS.ej_entity_strata_mapping

    enriched = pd.read_parquet(enriched_input)
    proposals = pd.read_parquet(proposals_input)

    required_variables = set(stratification_variables)
    missing_variables = sorted(required_variables.difference(enriched.columns))
    if missing_variables:
        raise KeyError(
            "Stage 01 enriched EJ consistency is missing stratification variables: "
            f"{missing_variables}"
        )

    if "stratum_id" in enriched.columns or "stratum_id" in proposals.columns:
        raise ValueError("Stage 01 EJ outputs must be unstratified.")

    if stratification_mode == "coding":
        strata_result = build_strata_from_variables(
            enriched,
            stratification_variables,
            names=names,
            variable_orders=stratification_orders,
        )
    elif stratification_mode == "mapping":
        mapping = load_table(mapping_path)
        strata_result = load_entity_strata_mapping(
            enriched,
            mapping,
            names=names,
            mapping_entity_id_column=entity_column,
            mapping_stratum_column="stratum_id",
            additional_columns=stratification_variables,
        )
        if not strata_result.missing_entity_assignments.empty:
            missing = to_user_columns(
                strata_result.missing_entity_assignments,
                names,
            ).head(20)
            raise ValueError(
                "The EJ mapping does not assign a stratum to every Stage 01 EJ. "
                f"Sample:\n{missing.to_string(index=False)}"
            )
    else:
        raise ValueError("stratification_mode must be 'coding' or 'mapping'.")

    stratum_codebook = validate_stratum_codebook(
        strata_result.stratum_codebook
    )

    stratified_enriched = attach_stratification(
        enriched,
        strata_result,
        source_label="enriched EJ consistency table",
    )
    stratified_proposals = attach_stratification(
        proposals,
        strata_result,
        source_label="EJ proposal table",
    )

    proposal_strata_per_ej = stratified_proposals.groupby(
        entity_column,
        dropna=False,
    )["stratum_id"].nunique(dropna=False)
    if not proposal_strata_per_ej.eq(1).all():
        raise ValueError("Every EJ must have exactly one stratum across proposal rows.")

    if stratified_proposals["statut_EJ_ANS"].isna().any():
        raise ValueError(
            "Stratified EJ proposals must expose missing statut_EJ_ANS as '<NA>'."
        )

    entity_assignments = strata_result.entity_assignments
    strata_plan = strata_result.strata_plan
    stratum_statistics = strata_plan.loc[
        :,
        ["stratum_id", *stratification_variables, ENTITY_COUNT],
    ].copy()

    log("EJ stratification")
    log(f"- mode: {stratification_mode}")
    log(f"- EJ assigned: {len(entity_assignments):,}")
    log(f"- observed strata: {len(strata_plan):,}")
    log(f"- codebook rows: {len(stratum_codebook):,}")
    log(f"- stratified proposal rows: {len(stratified_proposals):,}")

    output_paths = {}
    if write_outputs:
        output_dir.mkdir(parents=True, exist_ok=True)

        exported_assignments = to_user_columns(entity_assignments, names)
        exported_plan = to_user_columns(strata_plan, names)
        for table in (
            exported_assignments,
            exported_plan,
            stratified_enriched,
            stratified_proposals,
        ):
            table.attrs = {}

        exported_assignments.to_parquet(
            entity_assignments_output,
            index=False,
        )
        exported_plan.to_excel(
            strata_plan_output,
            sheet_name="strata_plan",
            index=False,
            engine="openpyxl",
        )
        stratified_enriched.to_parquet(
            stratified_enriched_output,
            index=False,
        )
        stratified_proposals.to_parquet(
            stratified_proposals_output,
            index=False,
        )
        export_stratum_codebook(codebook_output, stratum_codebook)

        output_paths = {
            "strata_plan": strata_plan_output,
            "entity_assignments": entity_assignments_output,
            "stratified_enriched_consistency": stratified_enriched_output,
            "stratified_proposals": stratified_proposals_output,
            "stratum_codebook": codebook_output,
        }
        log("Saved Stage 02 EJ outputs:")
        for output_path in output_paths.values():
            log(f"- {output_path}")
    else:
        log("write_outputs is False; no files were written.")

    return {
        "input_enriched": enriched,
        "input_proposals": proposals,
        "entity_assignments": entity_assignments,
        "strata_plan": strata_plan,
        "level_mapping": strata_result.level_mapping,
        "stratum_codebook": stratum_codebook,
        "stratum_statistics": stratum_statistics,
        "stratified_enriched_consistency": stratified_enriched,
        "stratified_proposals": stratified_proposals,
        "output_paths": output_paths,
    }


if __name__ == "__main__":
    run()
