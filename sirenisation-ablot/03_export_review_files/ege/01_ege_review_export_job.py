"""Export EGE review workbooks from the pooled EGE frame and final review plan.

The workbook layout is configured separately from :func:`run` so the operational
flow remains easy to read: load the pooled frame and plan, load optional prefill
decisions, export one complete review batch, then report compact counts.
"""

from __future__ import annotations


def build_review_config():
    from finess_sirene_review_export_engine import ReviewPipelineConfig

    IDENTIFICATION_COLS = [
        "EGE",
        "candidate_rank",
        "proposal_source",
        "is_initial_siret",
        "coherence_siren_du_siret_avec_siren_ej_corrige",
        "etat_siret",
        "siret_proposal",
    ]

    REVIEW_COLS = [
        "Siret_retenu",
        "Incertitude1",
        "Commentaire",
    ]

    INFO_COLS = [
        "EGE__rs",
        "siret__enseigne1Etablissement",
        "siren__denominationUniteLegale",
        "EGE__adresse",
        "siret__adresse",
        "EGE__libcategetab",
        "EGE__codeape",
        "EGE__intitule_naf",
        "siret__activitePrincipaleEtablissement",
        "siret__intitule_naf",
        "EGE__rslongue",
        "siret__denominationUsuelleEtablissement",
        "EGE__dateouv",
        "siret__dateCreationEtablissement",
    ]

    EGE_CONTEXT_COLS = [
        "datasets_consistency_EGE",
        "coherence_EGE_ANS",
        "statut_EGE_ANS",
        "statut_validation_Adrien_EGE",
    ]

    STRAT_COLS = [
        "EJ",
        "siren_ej_corrige",
        "EJ__rs",
        "EJ__coherence_EJ_ANS",
        "EJ__statut_EJ_ANS",
        "EJ__is_initial_siren_ANS",
        "EJ__statut_validation_Adrien",
        "EJ__datasets_consistency",
        "EJ__secteur_EJ",
        "stratum_id",
        "random_key",
        "reviewer",
    ]

    return ReviewPipelineConfig(
        entity_label="EGE",
        business_label="siret",
        entity_id_col="EGE",
        business_id_col="siret_proposal",
        identification_cols=IDENTIFICATION_COLS,
        review_cols=REVIEW_COLS,
        info_cols=INFO_COLS,
        context_cols=EGE_CONTEXT_COLS,
        strat_cols=STRAT_COLS,
        required_cols=("EJ",),
        date_cols=frozenset({
            "EGE__dateouv",
            "siret__dateCreationEtablissement",
        }),
        centered_cols=frozenset({
            "candidate_rank",
            "is_initial_siret",
            "datasets_consistency_EGE",
            "coherence_EGE_ANS",
            "statut_EGE_ANS",
            "coherence_siren_du_siret_avec_siren_ej_corrige",
            "EJ__datasets_consistency",
            "EJ__coherence_EJ_ANS",
            "EJ__statut_EJ_ANS",
            "EJ__is_initial_siren_ANS",
        }),
        entity_prefixes=("EGE__",),
        business_prefixes=("siret__", "siren__"),
        context_prefixes=("EJ__",),
        width_overrides={
            "EGE": 16,
            "candidate_rank": 10,
            "proposal_source": 14,
            "is_initial_siret": 14,
            "coherence_siren_du_siret_avec_siren_ej_corrige": 14,
            "etat_siret": 12,
            "siret_proposal": 18,
            "Siret_retenu": 18,
            "Incertitude1": 10,
            "Commentaire": 32,
            "EGE__codeape": 8,
            "siret__activitePrincipaleEtablissement": 8,
            "EGE__dateouv": 16,
            "siret__dateCreationEtablissement": 16,
            "EJ": 16,
            "siren_ej_corrige": 16,
            "stratum_id": 12,
            "reviewer": 14,
            "random_key": 14,
        },
        display_total=20,
    )


def run() -> dict[str, object]:
    import sys

    import pandas as pd

    from project_config import PATHS, PROJECT_ROOT

    module_dir = PROJECT_ROOT / "03_export_review_files"
    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))

    from finess_sirene_review_export_engine import (
        export_review_files,
        summarize_review_export,
    )

    config = build_review_config()

    pooled_proposals_path = PATHS.stage02_ege_pooled_proposals
    review_plan_path = PATHS.stage02_ege_review_plan
    prefill_path = PATHS.ege_additional_decisions
    output_root = PATHS.stage03_ege_review_export_root

    pooled_proposals = pd.read_parquet(pooled_proposals_path)
    review_plan = pd.read_excel(
        review_plan_path,
        usecols=["stratum_id", "reviewer", "sample_size"],
        dtype="string",
    )

    confirmed_decisions = None
    if prefill_path.exists():
        confirmed_decisions = pd.read_excel(
            prefill_path,
            usecols=["EGE", "Siret_retenu", "Incertitude1", "Commentaire"],
            dtype="string",
        )

    results = export_review_files(
        df=pooled_proposals,
        strata_plan=review_plan,
        output_root=output_root,
        config=config,
        confirmed_decisions=confirmed_decisions,
    )
    summary = summarize_review_export(
        results,
        review_plan,
        config,
        confirmed_decisions=confirmed_decisions,
    )

    print("EGE review export")
    print(f"- pooled EGE available: {pooled_proposals['EGE'].nunique(dropna=True):,}")
    print(f"- planned EGE reviews: {summary['planned_review_entity_count']:,}")
    print(
        "- EGE included in workbooks (review + following context): "
        f"{summary['exported_entity_count']:,}"
    )
    print(f"- prefilled EGE: {summary['prefilled_entity_count']:,}")
    print(
        f"- workbooks: {summary['workbook_count']:,} "
        f"across {summary['reviewer_count']:,} reviewer(s)"
    )
    print(f"- saved under: {output_root.resolve()}")

    return {
        "results": results,
        "summary": summary,
        "output_root": output_root,
    }


if __name__ == "__main__":
    run()
