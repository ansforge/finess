from __future__ import annotations

import pandas as pd
import pytest

from source_preprocessing.adrien import (
    ADRIEN_SOURCE_FLAG_COLUMNS,
    resolve_adrien_ege_duplicates,
)


def test_adrien_ege_duplicate_resolution_merges_evidence_but_blocks_conflicts():
    base = {
        "nofinesset": "000000001",
        "siret_prop": "11111111100001",
        "score_denomination_prop": 0.2,
        "source_siret_prop_nb": 1.0,
        "stable_field": "same",
        **{column: False for column in ADRIEN_SOURCE_FLAG_COLUMNS},
    }
    rows = pd.DataFrame(
        [
            {**base, ADRIEN_SOURCE_FLAG_COLUMNS[0]: True},
            {
                **base,
                "score_denomination_prop": 0.9,
                ADRIEN_SOURCE_FLAG_COLUMNS[1]: True,
            },
        ]
    )

    resolved, _ = resolve_adrien_ege_duplicates(rows)
    assert len(resolved) == 1
    assert resolved.loc[0, "score_denomination_prop"] == 0.9
    assert resolved.loc[0, "source_siret_prop_nb"] == 2.0
    assert resolved.loc[0, ADRIEN_SOURCE_FLAG_COLUMNS[:2]].all()

    conflicting = rows.copy()
    conflicting.loc[1, "stable_field"] = "different"
    with pytest.raises(ValueError, match="outside the documented evidence fields"):
        resolve_adrien_ege_duplicates(conflicting)
