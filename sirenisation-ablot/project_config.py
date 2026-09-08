"""Shared repository locations, data profile, and canonical artifact names.

The project is installed editable by ``uv sync``, so notebooks can import this
module regardless of their own directory. The ``dev`` profile selects the
relationship-preserving development paths; ``full`` remains the default. Explicit
root overrides still take precedence over profile defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _resolve_override(variable: str, default: Path) -> Path:
    value = os.environ.get(variable)
    return Path(value).expanduser().resolve() if value else default.resolve()


PROJECT_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class ProjectPaths:
    """Repository roots and the canonical artifacts used by stages 00–05."""

    project_root: Path
    data_profile: str
    data_root: Path
    source: Path
    study_inputs: Path
    reviewed: Path
    results: Path

    @classmethod
    def from_environment(cls) -> ProjectPaths:
        root = PROJECT_ROOT
        profile = os.environ.get("SIRENISATION_DATA_PROFILE", "full").strip().lower()
        if profile not in {"dev", "full"}:
            raise ValueError(
                "SIRENISATION_DATA_PROFILE must be either 'dev' or 'full', "
                f"not {profile!r}"
            )
        profile_root = root if profile == "full" else root / "dev"
        data_root = profile_root / "data"
        return cls(
            project_root=root,
            data_profile=profile,
            data_root=data_root.resolve(),
            source=_resolve_override(
                "SIRENISATION_DATA_ROOT",
                data_root / "source",
            ),
            study_inputs=_resolve_override(
                "SIRENISATION_STUDY_INPUTS_ROOT",
                data_root / "study_inputs",
            ),
            reviewed=_resolve_override(
                "SIRENISATION_REVIEWED_ROOT",
                data_root / "reviewed",
            ),
            results=_resolve_override(
                "SIRENISATION_RESULTS_ROOT",
                profile_root / "results",
            ),
        )

    @property
    def data(self) -> Path:
        """Alias for the source-data root used by existing jobs."""

        return self.source

    @property
    def data_study_inputs(self) -> Path:
        """Alias for the study-input root used by existing jobs."""

        return self.study_inputs

    @property
    def data_reviewed(self) -> Path:
        """Alias for the completed-review root used by existing jobs."""

        return self.reviewed

    @property
    def ej_review_root(self) -> Path:
        return self.reviewed / "ej"

    @property
    def ege_review_root(self) -> Path:
        return self.reviewed / "ege"

    @property
    def ej_additional_decisions(self) -> Path:
        """Independent supplementary EJ decisions input."""

        return self.study_inputs / "ej/ej_additional_confirmed_decisions.xlsx"

    @property
    def ege_additional_decisions(self) -> Path:
        """Independent supplementary EGE decisions input."""

        return self.study_inputs / "ege/ege_additional_confirmed_decisions.xlsx"

    @property
    def ej_entity_strata_mapping(self) -> Path:
        """Optional EJ -> stratum mapping used by Stage 02 mapping mode."""

        return self.study_inputs / "ej/ej_entity_strata_mapping.xlsx"

    @property
    def ej_stratum_reviewer_mapping(self) -> Path:
        return self.study_inputs / "ej/ej_stratum_reviewer_mapping.xlsx"

    @property
    def ege_stratum_reviewer_mapping(self) -> Path:
        return self.study_inputs / "ege/ege_stratum_reviewer_mapping.xlsx"

    @property
    def ej_sample_size_input(self) -> Path:
        return (
            self.study_inputs
            / "ej/ej_strata_plan_with_sample_size_input.xlsx"
        )

    @property
    def ege_sample_size_input(self) -> Path:
        return (
            self.study_inputs
            / "ege/ege_strata_plan_with_sample_size_input.xlsx"
        )

    @property
    def finess_ej_prepared(self) -> Path:
        return self.source / "finess_entites_juridiques/EntitesJuridiques_2026_05_04.parquet"

    @property
    def finess_ege_prepared(self) -> Path:
        return self.source / "finess_etablissements/EtablissementsGeolocalises_2026_05_04.parquet"

    @property
    def ans_ej_prepared(self) -> Path:
        return self.source / "ANS/df_ans_ej_valides.parquet"

    @property
    def ans_ege_prepared(self) -> Path:
        return self.source / "ANS/df_ans_ege_valides.parquet"

    @property
    def adrien_ej_prepared(self) -> Path:
        return self.source / "Adrien_Tortel/df_adrien_sirets_concordants_2026_06_sirenise.parquet"

    @property
    def adrien_ege_prepared(self) -> Path:
        return self.source / "Adrien_Tortel/df_adrien_sirets_concordants_2026_06_clean.parquet"

    @property
    def sirene_units_june(self) -> Path:
        return (
            self.source
            / "sirene_unites_legales/StockUniteLegale_2026_06_01.parquet"
        )

    @property
    def sirene_establishments_june(self) -> Path:
        return (
            self.source
            / "sirene_etablissements/StockEtablissement_2026_06_01.parquet"
        )

    @property
    def sirene_establishments_july(self) -> Path:
        return (
            self.source
            / "sirene_etablissements/StockEtablissement_2026_07_01.parquet"
        )

    @property
    def stage00_ej_filtered(self) -> Path:
        return (
            self.results
            / "00_prepare_data/finess/ej/EntitesJuridiques_2026_05_04_hors_EJ_sans_EGE.parquet"
        )

    @property
    def stage00_ej_excluded_without_ege(self) -> Path:
        return (
            self.results
            / "00_prepare_data/finess/ej/ej_excluded_without_ege.parquet"
        )

    @property
    def stage00_ej_prepared(self) -> Path:
        return (
            self.results
            / "00_prepare_data/finess/ej/EntitesJuridiques_2026_05_04_prepared.parquet"
        )

    @property
    def stage00_ege_prepared(self) -> Path:
        return (
            self.results
            / "00_prepare_data/finess/ege/EtablissementsGeolocalises_2026_05_04_clean.parquet"
        )

    @property
    def stage01_ej_consistency_enriched(self) -> Path:
        return (
            self.results
            / "01_build_reconciliation_tables/ej/ej_siren_consistency_enriched.parquet"
        )

    @property
    def stage01_ej_proposals_base(self) -> Path:
        return (
            self.results
            / "01_build_reconciliation_tables/ej/ej_siren_proposals_01_base.parquet"
        )

    @property
    def stage01_ej_proposals(self) -> Path:
        return self.results / "01_build_reconciliation_tables/ej/ej_siren_proposals.parquet"

    @property
    def stage01_ege_consistency_enriched(self) -> Path:
        return (
            self.results
            / "01_build_reconciliation_tables/ege/ege_siret_consistency_enriched.parquet"
        )

    @property
    def stage01_ege_proposals(self) -> Path:
        return self.results / "01_build_reconciliation_tables/ege/ege_siret_proposals.parquet"

    @property
    def stage02_ej_stratified_proposals(self) -> Path:
        return (
            self.results
            / "02_build_strata_plan/ej/ej_siren_proposals_stratified.parquet"
        )

    @property
    def stage02_ej_generated_plan(self) -> Path:
        return self.results / "02_build_strata_plan/ej/ej_strata_plan.xlsx"

    @property
    def stage02_ej_plan_with_reviewers(self) -> Path:
        return (
            self.results
            / "02_build_strata_plan/ej/ej_strata_plan_with_reviewers.xlsx"
        )

    @property
    def stage02_ej_review_plan(self) -> Path:
        return self.results / "02_build_strata_plan/ej/ej_strata_plan_with_sample_size.xlsx"

    @property
    def stage02_ege_generated_plan(self) -> Path:
        return self.results / "02_build_strata_plan/ege/ege_strata_plan.xlsx"

    @property
    def stage02_ege_plan_with_reviewers(self) -> Path:
        return (
            self.results
            / "02_build_strata_plan/ege/ege_strata_plan_with_reviewers.xlsx"
        )

    @property
    def stage02_ege_review_plan(self) -> Path:
        return self.results / "02_build_strata_plan/ege/ege_strata_plan_with_sample_size.xlsx"

    @property
    def stage02_ege_pooled_proposals(self) -> Path:
        return self.results / "02_build_strata_plan/ege/pooled_ege_proposals.parquet"

    @property
    def stage02_stratum_codebook(self) -> Path:
        return self.results / "02_build_strata_plan/stratum_codebook.xlsx"

    @property
    def stage03_ej_review_export_root(self) -> Path:
        return self.results / "03_export_review_files/ej/review_files"

    @property
    def stage03_ege_review_export_root(self) -> Path:
        return self.results / "03_export_review_files/ege/review_files"

    @property
    def stage04_ej_confirmed(self) -> Path:
        return self.results / "04_merge_reviews/ej/ej_confirmed_decisions.parquet"

    @property
    def stage04_ej_all_confirmed(self) -> Path:
        return self.results / "04_merge_reviews/ej/ej_all_confirmed_decisions.parquet"

    @property
    def stage04_ege_confirmed(self) -> Path:
        return self.results / "04_merge_reviews/ege/ege_confirmed_decisions.parquet"

    @property
    def stage04_ege_all_confirmed(self) -> Path:
        return self.results / "04_merge_reviews/ege/ege_all_confirmed_decisions.parquet"

    @property
    def stage05_ej_strata_analysis(self) -> Path:
        return self.results / "05_analyze_reviews/ej/ej_strata_plan_review_analysis.xlsx"

    @property
    def stage05_ej_summary(self) -> Path:
        return self.results / "05_analyze_reviews/ej/ej_global_review_summary.xlsx"

    @property
    def stage05_ege_strata_analysis(self) -> Path:
        return self.results / "05_analyze_reviews/ege/ege_strata_plan_review_analysis.xlsx"

    @property
    def stage05_ege_summary(self) -> Path:
        return self.results / "05_analyze_reviews/ege/ege_global_review_summary.xlsx"


PATHS = ProjectPaths.from_environment()
