"""Export EJ review workbooks from the final Stage 02 review plan.

The workbook layout is configured separately from :func:`run` so the operational
flow remains easy to read: load proposals and plan, load optional prefill decisions,
export one complete review batch, then report compact counts.
"""

from __future__ import annotations


def build_review_config():
    from finess_sirene_review_export_engine import (
        HyperlinkSpec,
        ReviewPipelineConfig,
        normalize_identifier,
    )

    IDENTIFICATION_COLS = [
        "EJ",
        "candidate_rank",
        "proposal_source",
        "is_initial_siren",
        "etat_siren",
        "siren_proposal",
    ]

    REVIEW_COLS = [
        "Siren_retenu",
        "Incertitude1",
        "Commentaire",
    ]

    INFO_COLS = [
        "finess__rs",
        "sirene__denominationUniteLegale",
        "finess__adresse_admin",
        "sirene__adresse_siege",
        "finess__codeape",
        "finess__intitule_naf",
        "sirene__activitePrincipaleUniteLegale",
        "sirene__intitule_naf",
        "finess__lien",
        "sirene__lien",
        "finess__rslongue",
        "sirene__denominationUsuelle1UniteLegale",
        "finess__statutjuridique",
        "finess__libstatutjuridique",
        "sirene__categorieJuridiqueUniteLegale",
        "sirene__libstatutjuridique",
        "finess__datecrea",
        "sirene__dateCreationUniteLegale",
    ]

    STRAT_COLS = [
        "coherence_EJ_ANS",
        "statut_EJ_ANS",
        "is_initial_siren_ANS",
        "statut_validation_Adrien",
        "datasets_consistency",
        "secteur_EJ",
        "stratum_id",
        "random_key",
        "reviewer",
    ]

    return ReviewPipelineConfig(
        entity_label="EJ",
        business_label="siren",
        entity_id_col="EJ",
        business_id_col="siren_proposal",
        identification_cols=IDENTIFICATION_COLS,
        review_cols=REVIEW_COLS,
        info_cols=INFO_COLS,
        strat_cols=STRAT_COLS,
        date_cols=frozenset({
            "finess__datecrea",
            "sirene__dateCreationUniteLegale",
        }),
        centered_cols=frozenset({
            "candidate_rank",
            "is_initial_siren",
            "coherence_EJ_ANS",
            "statut_EJ_ANS",
            "is_initial_siren_ANS",
            "datasets_consistency",
        }),
        entity_prefixes=("finess__",),
        business_prefixes=("sirene__",),
        width_overrides={
            "EJ": 16,
            "candidate_rank": 10,
            "proposal_source": 14,
            "is_initial_siren": 14,
            "etat_siren": 12,
            "siren_proposal": 16,
            "Siren_retenu": 16,
            "Incertitude1": 10,
            "Commentaire": 32,
            "finess__codeape": 8,
            "sirene__activitePrincipaleUniteLegale": 8,
            "finess__lien": 14,
            "sirene__lien": 14,
            "finess__statutjuridique": 8,
            "sirene__categorieJuridiqueUniteLegale": 8,
            "finess__datecrea": 16,
            "sirene__dateCreationUniteLegale": 16,
            "stratum_id": 12,
            "reviewer": 14,
            "random_key": 14,
        },
        hyperlinks={
            "sirene__lien": HyperlinkSpec(
                label=lambda row: f"Siren {normalize_identifier(row['business_id'])}",
                url=lambda row: (
                    "https://annuaire-entreprises.data.gouv.fr/entreprise/"
                    f"{normalize_identifier(row['business_id'])}"
                ),
                when=lambda row: bool(normalize_identifier(row["business_id"])),
            ),
            "finess__lien": HyperlinkSpec(
                label=lambda row: f"Finess {normalize_identifier(row['entity_id'])}",
                url=lambda row: (
                    "https://finess.esante.gouv.fr/fininter/jsp/"
                    "actionDetailEtablissement.do?noFiness="
                    f"{normalize_identifier(row['entity_id'])}"
                ),
                when=lambda row: (
                    normalize_identifier(row.get("candidate_rank")) == "1"
                    and bool(normalize_identifier(row["entity_id"]))
                ),
            ),
        },
        display_total=30,
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

    proposals_path = PATHS.stage02_ej_stratified_proposals
    review_plan_path = PATHS.stage02_ej_review_plan
    prefill_path = PATHS.ej_additional_decisions
    output_root = PATHS.stage03_ej_review_export_root

    proposals = pd.read_parquet(proposals_path)
    review_plan = pd.read_excel(
        review_plan_path,
        usecols=["stratum_id", "reviewer", "sample_size"],
        dtype="string",
    )

    confirmed_decisions = None
    if prefill_path.exists():
        confirmed_decisions = pd.read_excel(
            prefill_path,
            usecols=["EJ", "Siren_retenu", "Incertitude1", "Commentaire"],
            dtype="string",
        )

    results = export_review_files(
        df=proposals,
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

    print("EJ review export")
    print(f"- EJ available: {proposals['EJ'].nunique(dropna=True):,}")
    print(f"- planned EJ reviews: {summary['planned_review_entity_count']:,}")
    print(
        "- EJ included in workbooks (review + following context): "
        f"{summary['exported_entity_count']:,}"
    )
    print(f"- prefilled EJ: {summary['prefilled_entity_count']:,}")
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
