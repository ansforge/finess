from __future__ import annotations

import pandas as pd
import pytest
import reconciliation_strata_engine as strata


def test_coding_builds_complete_theoretical_codebook_and_explicit_missing_level():
    variables = ["dimension_a", "dimension_b"]
    orders = {
        "dimension_a": ["<NA>", "A"],
        "dimension_b": ["X", "Y", "Z"],
    }
    source = pd.DataFrame(
        {
            "EJ": ["000000001"],
            "dimension_a": [pd.NA],
            "dimension_b": ["Y"],
        }
    )

    result = strata.build_strata_from_variables(
        source,
        variables,
        names=strata.ReconciliationNames.ej_siren(entity_pad_width=9),
        variable_orders=orders,
    )

    # Coding keeps the full theoretical Cartesian product, not only observed strata.
    assert len(result.stratum_codebook) == 6
    assert result.stratum_codebook.columns.tolist() == ["stratum_id", *variables]
    assert set(result.stratum_codebook["dimension_a"]) == {"<NA>", "A"}
    assert set(result.stratum_codebook["dimension_b"]) == {"X", "Y", "Z"}

    assignment = strata.to_user_columns(
        result.entity_assignments,
        result.names,
    ).iloc[0]
    assert assignment["dimension_a"] == "<NA>"

    invalid = source.copy()
    invalid.loc[0, "dimension_b"] = "unexpected"
    with pytest.raises(ValueError):
        strata.build_strata_from_variables(
            invalid,
            variables,
            names=strata.ReconciliationNames.ej_siren(entity_pad_width=9),
            variable_orders=orders,
        )


def test_mapping_codebook_keeps_all_strata_from_complete_mapping():
    variables = ["dimension_a", "dimension_b"]
    source = pd.DataFrame({"EJ": ["000000001", "000000002"]})
    mapping = pd.DataFrame(
        {
            "EJ": ["000000001", "000000002", "999999999"],
            "stratum_id": ["A", "B", "C"],
            "dimension_a": [pd.NA, "A", "B"],
            "dimension_b": ["X", "Y", "Z"],
        }
    )

    result = strata.load_entity_strata_mapping(
        source,
        mapping,
        names=strata.ReconciliationNames.ej_siren(entity_pad_width=9),
        mapping_entity_id_column="EJ",
        additional_columns=variables,
    )

    # Stratum C is absent from the current source but must remain in the codebook.
    assert result.stratum_codebook.to_dict("records") == [
        {"stratum_id": "A", "dimension_a": "<NA>", "dimension_b": "X"},
        {"stratum_id": "B", "dimension_a": "A", "dimension_b": "Y"},
        {"stratum_id": "C", "dimension_a": "B", "dimension_b": "Z"},
    ]
    assert len(result.entity_assignments) == 2


def test_ege_plan_aggregates_already_inherited_strata():
    source = pd.DataFrame(
        {
            "EGE": ["000000001", "000000002", "000000003"],
            "stratum_id": ["121000", "121000", "221000"],
        }
    )

    result = strata.build_plan_from_existing_strata(
        source,
        names=strata.ReconciliationNames.ege_siret(),
    )
    plan = strata.to_user_columns(result.strata_plan, result.names)

    assert plan[["stratum_id", "n_EGE"]].to_dict("records") == [
        {"stratum_id": "121000", "n_EGE": 2},
        {"stratum_id": "221000", "n_EGE": 1},
    ]


@pytest.mark.parametrize(
    ("population_column", "maximum_column", "plan", "valid", "invalid"),
    [
        (
            "n_EJ",
            None,
            pd.DataFrame(
                {
                    "stratum_id": ["121000", "221000"],
                    "n_EJ": [10, 5],
                    "reviewer": ["A", "B"],
                }
            ),
            [3, 2],
            [11, 2],
        ),
        (
            "n_EGE",
            "n_EGE_pooled",
            pd.DataFrame(
                {
                    "stratum_id": ["121000", "221000"],
                    "n_EGE": [100, 50],
                    "n_EGE_pooled": [8, 0],
                    "reviewer": ["A", "B"],
                }
            ),
            [5, 0],
            [9, 0],
        ),
    ],
)
def test_sample_size_merge_enforces_the_available_population(
    population_column, maximum_column, plan, valid, invalid
):
    valid_input = pd.DataFrame(
        {
            "stratum_id": ["121000", "221000"],
            "sample_size": [str(value) for value in valid],
        }
    )
    result = strata.merge_sample_sizes_into_review_plan(
        plan,
        valid_input,
        population_column=population_column,
        maximum_sample_size_column=maximum_column,
    )
    assert result.strata_plan["sample_size"].tolist() == valid

    invalid_input = valid_input.copy()
    invalid_input["sample_size"] = [str(value) for value in invalid]
    expected_maximum = maximum_column or population_column
    with pytest.raises(ValueError, match=expected_maximum):
        strata.merge_sample_sizes_into_review_plan(
            plan,
            invalid_input,
            population_column=population_column,
            maximum_sample_size_column=maximum_column,
        )


def test_reviewer_mapping_reports_unassigned_strata():
    plan = pd.DataFrame(
        {
            "stratum_id": ["121000", "221000"],
            strata.ENTITY_COUNT: [10, 5],
        }
    )
    mapping = pd.DataFrame({"stratum_id": ["121000"], "reviewer": ["Alice"]})

    result = strata.load_stratum_reviewer_mapping(plan, mapping)

    assert result.strata_plan.set_index("stratum_id").loc["121000", "reviewer"] == "Alice"
    assert result.missing_reviewer_assignments["stratum_id"].tolist() == ["221000"]
