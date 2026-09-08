"""Build the base EGE-SIRET reconciliation and proposal table for Stage 01.

This job compares FINESS SIRET values with ANS and Adrien proposals, inherits
parent-EJ context, loads only the SIRENE establishments and legal units needed
by current candidates, and publishes the same Stage 01 artifacts consumed by
the following EGE enrichment and review-planning jobs.
"""

from __future__ import annotations


def run(
    *, write_outputs: bool = True, display_outputs: bool = True
) -> dict[str, object]:
    import json
    import sys

    import pandas as pd

    from project_config import PATHS, PROJECT_ROOT

    module_dir = PROJECT_ROOT / "01_build_reconciliation_tables"
    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))

    import ege_reconciliation as eger
    from finess_sirene_reconciliation import (
        EGE_SIRET_CONFIG,
        EJ_SIREN_CONFIG,
        build_consistency_table,
        build_proposal_table,
        compute_main_statistics,
        enrich_consistency_table,
        load_ege_siret_dataset,
        load_finess_database,
        load_sirene_database_for_identifiers,
    )
    from reconciliation_job_helpers import (
        assert_unique_key,
        collect_in_scope_business_identifiers,
        format_naf_code,
        load_lookup_series,
        validate_proposal_output,
        write_parquet_table,
    )

    log = print if display_outputs else lambda *_args, **_kwargs: None
    config = EGE_SIRET_CONFIG

    output_dir = PATHS.results / "01_build_reconciliation_tables/ege"
    raw_consistency_output = output_dir / "ege_siret_consistency_raw.parquet"
    enriched_consistency_output = PATHS.stage01_ege_consistency_enriched
    proposal_output = output_dir / "ege_siret_proposals_01_base.parquet"
    statistics_output = output_dir / "ege_siret_main_statistics.json"

    finess_keep_columns = [
        "siret",
        "rs",
        "rslongue",
        "codeape",
        "dateouv",
        "numvoie",
        "typvoie",
        "voie",
        "compvoie",
        "compldistrib",
        "lieuditbp",
        "ligneacheminement",
        "nofinessej",
    ]
    sirene_keep_columns = [
        "enseigne1Etablissement",
        "denominationUsuelleEtablissement",
        "activitePrincipaleEtablissement",
        "dateCreationEtablissement",
        "etatAdministratifEtablissement",
        "numeroVoieEtablissement",
        "indiceRepetitionEtablissement",
        "typeVoieEtablissement",
        "libelleVoieEtablissement",
        "codePostalEtablissement",
        "libelleCommuneEtablissement",
    ]

    # 1. Load FINESS and reconciliation sources.
    finess = load_finess_database(
        PATHS.stage00_ege_prepared,
        key_column="nofinesset",
        keep_columns=finess_keep_columns,
        config=config,
    )
    ans = load_ege_siret_dataset(
        PATHS.ans_ege_prepared,
        ege_column="nmfinessetab_stru",
        siret_column="siret_eg_retenu",
        dataset_name="ANS",
        keep_columns=["statut_eg", "phase_eg", "coherence"],
    )
    adrien = load_ege_siret_dataset(
        PATHS.adrien_ege_prepared,
        ege_column="nofinesset",
        siret_column="siret_prop",
        dataset_name="Adrien",
        keep_columns=[],
    )
    assert_unique_key(ans, "EGE", "ANS")

    # 2. Build the EGE reconciliation table and inherit the parent-EJ context.
    consistency = build_consistency_table(finess, ans, adrien, config=config)
    main_statistics = compute_main_statistics(consistency, config=config)

    enriched = enrich_consistency_table(
        consistency,
        finess_df=finess,
        dataset1_df=ans,
        dataset2_df=None,
        finess_columns=finess_keep_columns,
        dataset1_columns=["coherence", "statut_eg", "phase_eg", "siret"],
        dataset2_columns=None,
        config=config,
    )
    enriched = eger.add_derived_columns(enriched)

    parent_columns = [
        "EJ",
        "finess__rs",
        "coherence_EJ_ANS",
        "statut_EJ_ANS",
        "is_initial_siren_ANS",
        "statut_validation_Adrien",
        "datasets_consistency",
        "secteur_EJ",
        "stratum_id",
    ]
    ej_context = pd.read_parquet(
        PATHS.stage02_ej_stratified_proposals,
        columns=parent_columns,
    )
    enriched = eger.attach_parent_ej_context(enriched, ej_context)

    # 3. Load only SIRET that can occur in an in-scope proposal.
    requested_sirets = collect_in_scope_business_identifiers(
        finess,
        ans,
        adrien,
        entity_column="EGE",
        business_id_column="siret",
    )
    sirene_establishments = load_sirene_database_for_identifiers(
        PATHS.sirene_establishments_june,
        key_column="siret",
        identifiers=requested_sirets,
        keep_columns=sirene_keep_columns,
        config=config,
    )

    # 4. Build EGE proposals and their FINESS/SIRENE display enrichments.
    proposals = build_proposal_table(
        enriched,
        sirene_establishments,
        finess_df=finess,
        config=config,
        finess_entity_column="EGE",
        finess_business_id_column="siret",
        sirene_business_id_column="siret",
        sirene_columns=sirene_keep_columns,
        dataset1_name="ANS",
        dataset2_name="Adrien",
    )
    naf_labels = load_lookup_series(
        PATHS.source / "NAF/int_courts_naf_rev_2_clean.xlsx",
        code_column="Code",
        label_column="intitule_naf_65_caracteres",
        formatter=format_naf_code,
    )
    proposals = eger.prepare_proposals(proposals, naf_labels=naf_labels)

    # 5. Load only legal units referenced by the proposed SIRET values.
    requested_sirens = eger.sirens_from_siret_proposals(proposals)
    sirene_units = load_sirene_database_for_identifiers(
        PATHS.sirene_units_june,
        key_column="siren",
        identifiers=requested_sirens,
        keep_columns=["denominationUniteLegale"],
        config=EJ_SIREN_CONFIG,
    )
    proposals = eger.attach_siren_denomination(proposals, sirene_units)

    # 6. Compare each proposed SIRET with the confirmed SIREN of its parent EJ.
    ej_decisions_path = (
        PATHS.stage04_ej_all_confirmed
        if PATHS.stage04_ej_all_confirmed.exists()
        else PATHS.stage04_ej_confirmed
    )
    ej_decisions = pd.read_parquet(
        ej_decisions_path,
        columns=["EJ", "Siren_retenu"],
    )
    proposals = eger.attach_corrected_ej_reference(proposals, ej_decisions)
    proposals = eger.finalize_proposals(proposals)

    validate_proposal_output(
        enriched,
        proposals,
        entity_column="EGE",
        proposal_column="siret_proposal",
        initial_flag_column="is_initial_siret",
    )

    quality_summary = pd.DataFrame(
        {
            "metric": [
                "EGE in FINESS",
                "EGE in enriched consistency table",
                "proposal rows",
                "EGE with at least one proposal row",
                "distinct proposed SIRET values",
                "EGE matched to EJ enrichment",
            ],
            "value": [
                finess["EGE"].nunique(dropna=True),
                enriched["EGE"].nunique(dropna=True),
                len(proposals),
                proposals["EGE"].nunique(dropna=True),
                proposals.loc[
                    proposals["siret_proposal"].ne("N/A"),
                    "siret_proposal",
                ].nunique(dropna=True),
                enriched["has_ej_enrichment"].sum(),
            ],
        }
    )

    log("EGE-SIRET reconciliation")
    log(f"- FINESS EGE: {finess['EGE'].nunique(dropna=True):,}")
    log(
        "- relevant SIRET loaded: "
        f"{len(sirene_establishments):,} / {len(requested_sirets):,} requested"
    )
    log(
        "- relevant SIREN loaded: "
        f"{len(sirene_units):,} / {len(requested_sirens):,} requested"
    )
    log(f"- proposal rows: {len(proposals):,}")

    output_paths = [
        raw_consistency_output,
        enriched_consistency_output,
        proposal_output,
        statistics_output,
    ]
    if write_outputs:
        output_dir.mkdir(parents=True, exist_ok=True)
        write_parquet_table(consistency, raw_consistency_output)
        write_parquet_table(enriched, enriched_consistency_output)
        write_parquet_table(proposals, proposal_output)
        with statistics_output.open("w", encoding="utf-8") as file:
            json.dump(main_statistics, file, ensure_ascii=False, indent=2)
        log("- saved:")
        for path in output_paths:
            log(f"  - {path}")
    else:
        log("- write_outputs is False; no files were written.")

    return {
        "finess": finess,
        "consistency": consistency,
        "enriched_consistency": enriched,
        "proposals": proposals,
        "quality_summary": quality_summary,
        "main_statistics": main_statistics,
        "output_paths": output_paths if write_outputs else [],
    }


if __name__ == "__main__":
    run()
