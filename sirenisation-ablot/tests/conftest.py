from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# The numbered workflow directories are not Python package names. Add their
# shared-module roots once here instead of repeating path manipulation in tests.
for directory in (
    ROOT,
    ROOT / "project_tools",
    ROOT / "00_prepare_data",
    ROOT / "01_build_reconciliation_tables",
    ROOT / "02_build_strata_plan",
    ROOT / "03_export_review_files",
    ROOT / "04_merge_reviews",
    ROOT / "05_analyze_reviews",
):
    path = str(directory)
    if path not in sys.path:
        sys.path.insert(0, path)


@pytest.fixture
def ej_review_config():
    import finess_sirene_review_export_engine as review_export

    return review_export.ReviewPipelineConfig(
        entity_label="EJ",
        business_label="SIREN",
        entity_id_col="EJ",
        business_id_col="siren_proposal",
        identification_cols=("EJ", "candidate_rank", "siren_proposal"),
        review_cols=("Siren_retenu", "Incertitude1", "Commentaire"),
        info_cols=(),
        strat_cols=("stratum_id", "random_key", "reviewer"),
        display_total=3,
    )


@pytest.fixture
def ej_review_inputs(ej_review_config):
    import pandas as pd

    proposals = pd.DataFrame(
        [
            {
                "EJ": "000000001",
                "candidate_rank": 1,
                "siren_proposal": "111111111",
                "stratum_id": "000001",
                "random_key": 0.2,
            },
            {
                "EJ": "000000001",
                "candidate_rank": 2,
                "siren_proposal": "222222222",
                "stratum_id": "000001",
                "random_key": 0.2,
            },
            {
                "EJ": "000000002",
                "candidate_rank": 1,
                "siren_proposal": "333333333",
                "stratum_id": "000001",
                "random_key": 0.1,
            },
            {
                "EJ": "000000002",
                "candidate_rank": 2,
                "siren_proposal": "444444444",
                "stratum_id": "000001",
                "random_key": 0.1,
            },
        ]
    )
    review_plan = pd.DataFrame(
        [{"stratum_id": "000001", "reviewer": "tester", "sample_size": 1}]
    )
    return proposals, review_plan, ej_review_config
