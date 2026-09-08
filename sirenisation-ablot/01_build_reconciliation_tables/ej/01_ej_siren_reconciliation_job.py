"""Build the base EJ-SIREN reconciliation and proposal table for Stage 01.

This job compares in-scope FINESS SIREN values with ANS and Adrien proposals,
loads only the SIRENE legal units that can become candidates, enriches the
reconciliation outputs, and publishes the same Stage 01 artifacts consumed by
the following EJ enrichment and stratification jobs.
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

    import ej_reconciliation as ejr
    from finess_sirene_reconciliation import (
        EJ_SIREN_CONFIG,
        build_consistency_table,
        build_proposal_table,
        compute_main_statistics,
        enrich_consistency_table,
        load_ej_siren_dataset,
        load_finess_database,
        load_sirene_database_for_identifiers,
    )
    from reconciliation_job_helpers import (
        assert_unique_key,
        collect_in_scope_business_identifiers,
        format_naf_code,
        load_lookup_series,
        normalize_integer_code,
        validate_proposal_output,
        write_parquet_table,
    )

    log = print if display_outputs else lambda *_args, **_kwargs: None
    config = EJ_SIREN_CONFIG

    output_dir = PATHS.results / "01_build_reconciliation_tables/ej"
    raw_consistency_output = output_dir / "ej_siren_consistency_raw.parquet"
    enriched_consistency_output = PATHS.stage01_ej_consistency_enriched
    proposal_output = output_dir / "ej_siren_proposals_01_base.parquet"
    statistics_output = output_dir / "ej_siren_main_statistics.json"

    finess_keep_columns = [
        "siren",
        "rs",
        "rslongue",
        "statutjuridique",
        "libstatutjuridique",
        "codeape",
        "datecrea",
        "ehpad_hopitaux",
        "numvoie",
        "typvoie",
        "voie",
        "compvoie",
        "compldistrib",
        "lieuditbp",
        "ligneacheminement",
    ]
    sirene_keep_columns = [
        "denominationUniteLegale",
        "denominationUsuelle1UniteLegale",
        "categorieJuridiqueUniteLegale",
        "activitePrincipaleUniteLegale",
        "dateCreationUniteLegale",
        "etatAdministratifUniteLegale",
    ]

    # 1. Load FINESS and reconciliation sources.
    finess = load_finess_database(
        PATHS.stage00_ej_prepared,
        key_column="nofiness",
        keep_columns=finess_keep_columns,
        config=config,
    )
    excluded_ej = pd.read_parquet(
        PATHS.stage00_ej_excluded_without_ege,
        columns=["nofiness"],
    )
    ans = load_ej_siren_dataset(
        PATHS.ans_ej_prepared,
        ej_column="nmfinessej_ej",
        siren_column="siren_ej_retenu",
        dataset_name="ANS",
        keep_columns=["statut_ej", "phase_ej", "coherence"],
    )
    adrien = load_ej_siren_dataset(
        PATHS.adrien_ej_prepared,
        ej_column="nofinessej",
        siren_column="siren_prop",
        dataset_name="Adrien",
        keep_columns=[],
    )
    assert_unique_key(ans, "EJ", "ANS")

    # 2. Build and enrich the EJ-level reconciliation table.
    consistency = build_consistency_table(
        finess,
        ans,
        adrien,
        config=config,
        known_out_of_scope_entities=excluded_ej["nofiness"].dropna().tolist(),
    )
    main_statistics = compute_main_statistics(consistency, config=config)

    enriched = enrich_consistency_table(
        consistency,
        finess_df=finess,
        dataset1_df=ans,
        dataset2_df=None,
        finess_columns=finess_keep_columns,
        dataset1_columns=["coherence", "statut_ej", "phase_ej", "siren"],
        dataset2_columns=None,
        config=config,
    )
    enriched = ejr.add_derived_columns(enriched)

    # 3. Load only SIREN that can occur in an in-scope proposal.
    requested_sirens = collect_in_scope_business_identifiers(
        finess,
        ans,
        adrien,
        entity_column="EJ",
        business_id_column="siren",
    )
    sirene = load_sirene_database_for_identifiers(
        PATHS.sirene_units_june,
        key_column="siren",
        identifiers=requested_sirens,
        keep_columns=sirene_keep_columns,
        config=config,
    )

    # 4. Build proposals and apply the stable Stage 01 output schema.
    proposals = build_proposal_table(
        enriched,
        sirene,
        finess_df=finess,
        config=config,
        finess_entity_column="EJ",
        finess_business_id_column="siren",
        sirene_business_id_column="siren",
        sirene_columns=sirene_keep_columns,
        dataset1_name="ANS",
        dataset2_name="Adrien",
    )

    legal_status_labels = load_lookup_series(
        PATHS.source / "statut_juridique/statutjuridique_lib_2022_09.xlsx",
        code_column="Code",
        label_column="Libellé",
        formatter=normalize_integer_code,
    )
    naf_labels = load_lookup_series(
        PATHS.source / "NAF/int_courts_naf_rev_2_clean.xlsx",
        code_column="Code",
        label_column="intitule_naf_65_caracteres",
        formatter=format_naf_code,
    )
    proposals = ejr.finalize_proposals(
        proposals,
        legal_status_labels=legal_status_labels,
        naf_labels=naf_labels,
    )

    # Stage 01 publishes only the public names consumed by Stage 02.
    enriched = ejr.finalize_enriched_consistency(enriched)

    validate_proposal_output(
        enriched,
        proposals,
        entity_column="EJ",
        proposal_column="siren_proposal",
        initial_flag_column="is_initial_siren",
    )

    quality_summary = pd.DataFrame(
        {
            "metric": [
                "EJ in FINESS",
                "EJ in raw consistency table",
                "EJ in enriched consistency table",
                "proposal rows",
                "EJ with at least one proposal row",
                "distinct proposed SIREN values",
            ],
            "value": [
                finess["EJ"].nunique(dropna=True),
                consistency["EJ"].nunique(dropna=True),
                enriched["EJ"].nunique(dropna=True),
                len(proposals),
                proposals["EJ"].nunique(dropna=True),
                proposals.loc[
                    proposals["siren_proposal"].ne("N/A"),
                    "siren_proposal",
                ].nunique(dropna=True),
            ],
        }
    )

    log("EJ-SIREN reconciliation")
    log(f"- FINESS EJ: {finess['EJ'].nunique(dropna=True):,}")
    log(f"- relevant SIREN loaded: {len(sirene):,} / {len(requested_sirens):,} requested")
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
