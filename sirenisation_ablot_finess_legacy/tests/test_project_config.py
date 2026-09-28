from __future__ import annotations

from pathlib import Path

import pytest

from project_config import ProjectPaths

ROOT = Path(__file__).resolve().parents[1]


def _clear_overrides(monkeypatch):
    for name in (
        "SIRENISATION_DATA_ROOT",
        "SIRENISATION_STUDY_INPUTS_ROOT",
        "SIRENISATION_REVIEWED_ROOT",
        "SIRENISATION_RESULTS_ROOT",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize(
    ("profile", "profile_root"),
    [("full", ROOT), ("dev", ROOT / "dev")],
)
def test_profiles_and_selected_canonical_paths(monkeypatch, profile, profile_root):
    _clear_overrides(monkeypatch)
    monkeypatch.setenv("SIRENISATION_DATA_PROFILE", profile)

    paths = ProjectPaths.from_environment()
    data_root = profile_root / "data"

    assert paths.data_profile == profile
    assert paths.data_root == data_root.resolve()
    assert paths.source == (data_root / "source").resolve()
    assert paths.study_inputs == (data_root / "study_inputs").resolve()
    assert paths.reviewed == (data_root / "reviewed").resolve()
    assert paths.results == (profile_root / "results").resolve()

    # Compatibility aliases are still part of the maintained API.
    assert paths.data == paths.source
    assert paths.data_study_inputs == paths.study_inputs
    assert paths.data_reviewed == paths.reviewed

    assert paths.stage00_ej_excluded_without_ege == (
        paths.results / "00_prepare_data/finess/ej/ej_excluded_without_ege.parquet"
    )
    assert paths.stage01_ej_proposals == (
        paths.results / "01_build_reconciliation_tables/ej/ej_siren_proposals.parquet"
    )
    assert paths.stage02_ej_review_plan == (
        paths.results / "02_build_strata_plan/ej/ej_strata_plan_with_sample_size.xlsx"
    )
    assert paths.stage02_ege_pooled_proposals == (
        paths.results / "02_build_strata_plan/ege/pooled_ege_proposals.parquet"
    )
    assert paths.stage03_ej_review_export_root == (
        paths.results / "03_export_review_files/ej/review_files"
    )
    assert paths.stage04_ej_all_confirmed == (
        paths.results / "04_merge_reviews/ej/ej_all_confirmed_decisions.parquet"
    )
    assert paths.stage04_ege_all_confirmed == (
        paths.results / "04_merge_reviews/ege/ege_all_confirmed_decisions.parquet"
    )
    assert paths.stage05_ej_strata_analysis == (
        paths.results / "05_analyze_reviews/ej/ej_strata_plan_review_analysis.xlsx"
    )
    assert paths.stage05_ege_summary == (
        paths.results / "05_analyze_reviews/ege/ege_global_review_summary.xlsx"
    )


def test_invalid_profile_is_rejected(monkeypatch):
    _clear_overrides(monkeypatch)
    monkeypatch.setenv("SIRENISATION_DATA_PROFILE", "invalid")
    with pytest.raises(ValueError, match="dev.*full|full.*dev"):
        ProjectPaths.from_environment()
