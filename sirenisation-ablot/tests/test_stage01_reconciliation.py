from __future__ import annotations

import warnings

import finess_sirene_reconciliation as reconciliation
import pandas as pd
import pytest


def _source(frame, name):
    frame.attrs["dataset_name"] = name
    return frame


def test_consistency_types_and_main_statistics():
    finess = pd.DataFrame(
        {
            "EJ": ["000000001", "000000002", "000000003"],
            "siren": ["111111111", "222222222", pd.NA],
        }
    )
    ans = _source(
        pd.DataFrame(
            {
                "EJ": ["000000001", "000000002", "000000003"],
                "siren": ["111111111", "999999999", "333333333"],
            }
        ),
        "ANS",
    )
    adrien = _source(
        pd.DataFrame(
            {
                "EJ": ["000000001", "000000002", "000000002"],
                "siren": ["111111111", "999999999", "888888888"],
            }
        ),
        "Adrien",
    )

    table = reconciliation.build_consistency_table(
        finess, ans, adrien, config=reconciliation.EJ_SIREN_CONFIG
    )

    assert table["consistency_type"].tolist() == [
        "Total consistency",
        "Partial consistency",
        "Total inconsistency",
    ]

    stats = reconciliation.compute_main_statistics(
        table, config=reconciliation.EJ_SIREN_CONFIG
    )["all_finess_entities"]
    assert stats["total_consistency_n"] == 1
    assert stats["partial_consistency_n"] == 1
    assert stats["total_inconsistency_n"] == 1


def test_stage00_exclusions_are_not_reported_as_unexpected_orphans():
    finess = pd.DataFrame({"EJ": ["000000001"]})
    ans = _source(
        pd.DataFrame(
            {
                "EJ": ["000000001", "000000002", "000000003"],
                "siren": ["111111111", "222222222", "333333333"],
            }
        ),
        "ANS",
    )
    adrien = _source(
        pd.DataFrame({"EJ": ["000000001"], "siren": ["111111111"]}),
        "Adrien",
    )

    with pytest.warns(UserWarning, match=r"1 EJ\(s\).*unexpectedly absent"):
        table = reconciliation.build_consistency_table(
            finess,
            ans,
            adrien,
            config=reconciliation.EJ_SIREN_CONFIG,
            known_out_of_scope_entities={"000000002"},
        )

    assert table.attrs["dataset1_orphan_entity_count"] == 2
    assert table.attrs["dataset1_out_of_scope_entity_count"] == 1
    assert table.attrs["dataset1_unexpected_orphan_entity_count"] == 1

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        explained = reconciliation.build_consistency_table(
            finess,
            ans.loc[ans["EJ"].ne("000000003")].copy(),
            adrien,
            config=reconciliation.EJ_SIREN_CONFIG,
            known_out_of_scope_entities={"2"},
        )

    assert explained.attrs["dataset1_unexpected_orphan_entity_count"] == 0
    assert caught == []


def test_proposal_table_keeps_initial_and_deduplicates_shared_sources():
    finess = pd.DataFrame(
        {
            "EJ": ["000000001", "000000002", "000000003"],
            "siren": ["111111111", "222222222", pd.NA],
        }
    )
    ans = _source(
        pd.DataFrame(
            {
                "EJ": ["000000001", "000000002", "000000003"],
                "siren": ["111111111", "999999999", "333333333"],
            }
        ),
        "ANS",
    )
    adrien = _source(
        pd.DataFrame(
            {
                "EJ": ["000000001", "000000002", "000000002"],
                "siren": ["111111111", "999999999", "888888888"],
            }
        ),
        "Adrien",
    )
    consistency = reconciliation.build_consistency_table(
        finess, ans, adrien, config=reconciliation.EJ_SIREN_CONFIG
    )
    sirene = pd.DataFrame(
        {
            "siren": [
                "111111111",
                "222222222",
                "999999999",
                "333333333",
                "888888888",
            ],
            "denomination": ["a", "b", "x", "c", "y"],
        }
    )

    proposals = reconciliation.build_proposal_table(
        consistency,
        sirene,
        finess_df=finess,
        config=reconciliation.EJ_SIREN_CONFIG,
        sirene_columns=["denomination"],
    )

    ej2 = proposals.loc[proposals["EJ"].eq("000000002")]
    assert ej2[["siren_proposal", "proposal_source", "candidate_rank"]].to_dict(
        "records"
    ) == [
        {
            "siren_proposal": "222222222",
            "proposal_source": "none",
            "candidate_rank": 1,
        },
        {
            "siren_proposal": "999999999",
            "proposal_source": "both",
            "candidate_rank": 2,
        },
        {
            "siren_proposal": "888888888",
            "proposal_source": "Adrien",
            "candidate_rank": 3,
        },
    ]
    assert ej2["is_initial_siren"].tolist() == [True, False, False]

    ej3 = proposals.loc[proposals["EJ"].eq("000000003")]
    assert ej3.iloc[0]["siren_proposal"] == "N/A"
    assert bool(ej3.iloc[0]["is_initial_siren"])


def test_parent_enrichment_collapses_duplicates_and_blocks_conflicts():
    parent_rows = pd.DataFrame(
        [
            {"EJ": "000000001", "stratum_id": "000100", "sector": "other"},
            {"EJ": "000000001", "stratum_id": "000100", "sector": "other"},
            {"EJ": "000000002", "stratum_id": "000200", "sector": pd.NA},
        ]
    )

    enrichment = reconciliation.validated_parent_enrichment(
        parent_rows,
        parent_column="EJ",
        inherited_columns=("stratum_id", "sector"),
        source="synthetic EJ proposals",
    )
    assert enrichment["EJ"].tolist() == ["000000001", "000000002"]

    conflicting = parent_rows.copy()
    conflicting.loc[1, "stratum_id"] = "999999"
    with pytest.raises(ValueError, match="conflicting fields within EJ groups"):
        reconciliation.validated_parent_enrichment(
            conflicting,
            parent_column="EJ",
            inherited_columns=("stratum_id", "sector"),
            source="synthetic EJ proposals",
        )
