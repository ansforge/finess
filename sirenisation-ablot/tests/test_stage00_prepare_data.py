from __future__ import annotations

import pandas as pd
from finess_scope import (
    add_hospital_ehpad_flag,
    filter_ege_to_known_parents,
    split_ej_analysis_scope,
)


def test_ej_scope_separates_ej_without_child_ege():
    ej = pd.DataFrame({"nofiness": ["A", "B", "C"], "label": ["a", "b", "c"]})
    ege = pd.DataFrame({"nofinessej": ["A", "B", "B"]})

    retained, excluded = split_ej_analysis_scope(ej, ege)

    assert retained["nofiness"].tolist() == ["A", "B"]
    assert excluded["nofiness"].tolist() == ["C"]
    assert retained.columns.tolist() == ej.columns.tolist()
    assert excluded.columns.tolist() == ej.columns.tolist()


def test_ege_scope_keeps_only_ege_with_known_parent():
    ej = pd.DataFrame({"nofiness": ["A", "B"]})
    ege = pd.DataFrame(
        {
            "nofinesset": ["E1", "E2", "E3"],
            "nofinessej": ["A", "C", "B"],
        }
    )

    retained = filter_ege_to_known_parents(ege, ej)

    assert retained["nofinesset"].tolist() == ["E1", "E3"]


def test_hospital_ehpad_flag_uses_any_child_ege():
    ej = pd.DataFrame({"nofiness": ["A", "B", "C"]})
    ege = pd.DataFrame(
        {
            "nofinessej": ["A", "A", "B"],
            "categetab": ["9999", "500", "9999"],
        }
    )

    enriched = add_hospital_ehpad_flag(ej, ege)
    flags = enriched.set_index("nofiness")["ehpad_hopitaux"].to_dict()

    assert flags == {"A": True, "B": False, "C": False}
