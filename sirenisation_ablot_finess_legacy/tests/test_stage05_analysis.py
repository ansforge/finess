from __future__ import annotations

import analyze_reviews as analysis
import finite_population_wilson_ci as wilson
import numpy as np
import pandas as pd
import pytest
import review_global_summary as global_summary
import sampling_precision


def test_ege_pooled_frame_matches_plan_and_blocks_stale_counts():
    plan = pd.DataFrame(
        {
            "stratum_id": ["121000", "221000", "321000"],
            "n_EGE": [10, 20, 5],
            "n_EGE_pooled": [2, 1, 0],
        }
    )
    pooled = pd.DataFrame(
        {
            "EGE": ["E1", "E1", "E2", "E3"],
            "stratum_id": ["121000", "121000", "121000", "221000"],
        }
    )

    summary = analysis.validate_ege_pooled_frame_against_plan(plan, pooled)
    assert summary == {
        "pooled_ege_count": 3,
        "pooled_strata_count": 2,
        "plan_strata_count": 3,
    }

    stale_plan = plan.copy()
    stale_plan.loc[0, "n_EGE_pooled"] = 1
    with pytest.raises(analysis.DataValidationError, match="does not match"):
        analysis.validate_ege_pooled_frame_against_plan(stale_plan, pooled)


def test_ege_two_stage_weight_identity():
    ej_plan = pd.DataFrame([{"stratum_id": "000001", "n_EJ": 4}])
    ej_confirmed = pd.DataFrame(
        [
            {"EJ": "000000001", "stratum_id": "000001"},
            {"EJ": "000000002", "stratum_id": "000001"},
        ]
    )
    pooled = pd.DataFrame(
        [
            {"EGE": "100000001", "EJ": "000000001", "stratum_id": "000001"},
            {"EGE": "100000002", "EJ": "000000001", "stratum_id": "000001"},
            {"EGE": "100000003", "EJ": "000000002", "stratum_id": "000001"},
            {"EGE": "100000004", "EJ": "000000002", "stratum_id": "000001"},
        ]
    )
    proposals = pd.DataFrame(
        [
            {
                "EGE": ege,
                "siret_proposal": siret,
                "proposal_source": "Initial",
                "stratum_id": "000001",
                "statut_validation_Adrien_EGE": "0 proposition",
                "is_initial_siret": True,
            }
            for ege, siret in [
                ("100000001", "11111111100001"),
                ("100000002", "11111111100002"),
                ("100000003", "22222222200001"),
                ("100000004", "22222222200002"),
            ]
        ]
    )
    confirmed = pd.DataFrame(
        [
            {
                "EGE": "100000001",
                "stratum_id": "000001",
                "Siret_retenu": "11111111100001",
                "Incertitude1": "0",
                "Commentaire": "",
            },
            {
                "EGE": "100000003",
                "stratum_id": "000001",
                "Siret_retenu": "22222222200001",
                "Incertitude1": "0",
                "Commentaire": "",
            },
        ]
    )
    ege_plan = pd.DataFrame([{"stratum_id": "000001", "n_EGE": 8}])

    per_stratum = analysis.analyze_confirmed_decisions(
        confirmed,
        proposals,
        config=analysis.EGE_SIRET_CONFIG,
    )
    design = analysis.build_ege_two_stage_sampling_design(
        ej_plan,
        ej_confirmed,
        pooled,
        ej_population_size_column="n_EJ",
    )
    enriched = analysis.enrich_strata_plan(
        ege_plan,
        per_stratum,
        config=analysis.EGE_SIRET_CONFIG,
        ege_sampling_design_df=design,
    )

    names = analysis.EGE_SIRET_CONFIG.analysis_columns
    represented = enriched.loc[enriched[names["reviewed"]].gt(0)]
    product = (
        represented[names["first_stage_inclusion_probability"]]
        * represented[names["second_stage_inclusion_probability"]]
        * represented[names["sampling_weight"]]
    )
    assert np.allclose(product, 1.0, rtol=2e-6, atol=2e-6)


def test_na_with_closure_uncertainty_is_classified_to_close():
    outcomes = analysis.build_entity_review_outcomes(
        pd.DataFrame(
            [
                {
                    "EJ": "000000001",
                    "stratum_id": "000001",
                    "Siren_retenu": "NA",
                    "Incertitude1": "-2",
                    "Commentaire": "closure",
                }
            ]
        ),
        pd.DataFrame(
            [
                {
                    "EJ": "000000001",
                    "siren_proposal": "N/A",
                    "proposal_source": "none",
                    "stratum_id": "000001",
                    "statut_validation_Adrien": "0 proposition",
                    "is_initial_siren": True,
                }
            ]
        ),
        config=analysis.EJ_SIREN_CONFIG,
    )

    assert int(outcomes.loc[0, "to_close"]) == 1
    assert int(outcomes.loc[0, "with_uncertainty"]) == 1


def test_global_consistency_checks_accounting_and_population():
    plan = pd.DataFrame({"stratum_id": ["121000"], "n_EJ": [3]})
    proposals = pd.DataFrame({"EJ": ["J1", "J2", "J3"]})
    summary = pd.DataFrame(
        [
            {
                "Metric": "Initial correct",
                "Population count": 1.5,
                "Proportion (%)": 75.0,
                "Denominator": "EJs to match",
                "Denominator population": 2.0,
                "Basis": "test",
            },
            {
                "Metric": "EJs to close",
                "Population count": 1.0,
                "Proportion (%)": 33.33,
                "Denominator": "EJs examined",
                "Denominator population": 3.0,
                "Basis": "test",
            },
        ],
        columns=global_summary.GLOBAL_METRIC_COLUMNS,
    )
    scenarios = pd.DataFrame(
        {
            "Estimated mistakes corrected in accepted strata": [2.0],
            "Estimated mistakes introduced in accepted strata": [0.5],
            "Gain vs Initial (estimated entities)": [1.5],
        }
    )

    result = global_summary.validate_global_analysis_consistency(
        proposals,
        plan,
        summary,
        scenarios,
        config=analysis.EJ_SIREN_CONFIG,
    )
    assert result["known_population"] == 3.0
    assert result["match_population"] == 2.0
    assert result["close_population"] == 1.0

    invalid = scenarios.copy()
    invalid["Gain vs Initial (estimated entities)"] = 1.0
    with pytest.raises(analysis.DataValidationError, match="net gain"):
        global_summary.validate_global_analysis_consistency(
            proposals,
            plan,
            summary,
            invalid,
            config=analysis.EJ_SIREN_CONFIG,
        )


def test_finite_population_helpers_cover_census_and_empty_sample():
    assert wilson.finite_population_wilson_ci(10, 10, 7) == (0.7, 0.7)
    assert sampling_precision.finite_population_margin_of_error_pct(10, 10) == 0.0
    assert sampling_precision.finite_population_margin_of_error_pct(0, 10) is None

    with pytest.raises(ValueError, match="cannot exceed"):
        wilson.finite_population_wilson_ci(5, 6, 3)
