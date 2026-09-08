"""Pure FINESS scope transformations used by Stage 00 jobs."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

HOSPITAL_CATEGORIES = frozenset(
    map(
        str,
        [
            101, 106, 109, 114, 115, 122, 127, 128, 129, 131, 141, 146,
            156, 161, 292, 355, 362, 365, 366, 412, 415, 422, 425, 426,
            430, 433, 444, 695, 696, 697, 698, 699, 899, 999,
        ],
    )
)
EHPAD_CATEGORIES = frozenset({"500", "501", "502"})
HOSPITAL_EHPAD_CATEGORIES = HOSPITAL_CATEGORIES | EHPAD_CATEGORIES


def split_ej_analysis_scope(
    ej: pd.DataFrame,
    ege: pd.DataFrame,
    *,
    ej_id_column: str = "nofiness",
    ege_parent_column: str = "nofinessej",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split FINESS EJ into the analysis scope and EJ without a linked EGE."""
    linked_ej_ids = set(ege[ege_parent_column].dropna())
    in_scope = ej[ej_id_column].isin(linked_ej_ids)
    return ej.loc[in_scope].copy(), ej.loc[~in_scope].copy()


def filter_ege_to_known_parents(
    ege: pd.DataFrame,
    ej: pd.DataFrame,
    *,
    ege_parent_column: str = "nofinessej",
    ej_id_column: str = "nofiness",
) -> pd.DataFrame:
    """Keep only EGE whose parent EJ exists in the supplied FINESS EJ table."""
    valid_ej_ids = set(ej[ej_id_column].dropna())
    return ege.loc[ege[ege_parent_column].isin(valid_ej_ids)].copy()


def add_hospital_ehpad_flag(
    ej: pd.DataFrame,
    ege: pd.DataFrame,
    *,
    ej_id_column: str = "nofiness",
    ege_parent_column: str = "nofinessej",
    category_column: str = "categetab",
    categories: Iterable[str] = HOSPITAL_EHPAD_CATEGORIES,
) -> pd.DataFrame:
    """Flag an EJ when at least one child EGE is a hospital or EHPAD.

    The merge intentionally preserves the same public columns as the existing
    Stage 00 job, including the right-hand ``nofinessej`` key.
    """
    ej_work = ej.copy()
    ege_work = ege.copy()
    ej_work[ej_id_column] = ej_work[ej_id_column].astype(str)
    ege_work[ege_parent_column] = ege_work[ege_parent_column].astype(str)

    category_values = {str(value) for value in categories}
    flag_by_ej = (
        ege_work.assign(_flag=ege_work[category_column].astype(str).isin(category_values))
        .groupby(ege_parent_column, as_index=False)["_flag"]
        .any()
        .rename(columns={"_flag": "ehpad_hopitaux"})
    )

    enriched = ej_work.merge(
        flag_by_ej,
        how="left",
        left_on=ej_id_column,
        right_on=ege_parent_column,
    )
    enriched["ehpad_hopitaux"] = enriched["ehpad_hopitaux"].eq(True)
    return enriched
