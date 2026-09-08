"""Small shared helpers for the Stage 01 reconciliation jobs."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def assert_unique_key(df: pd.DataFrame, key: str, label: str) -> None:
    """Raise when a table expected to contain one row per key is not unique."""
    duplicated = df.duplicated(key, keep=False)
    if duplicated.any():
        sample = df.loc[duplicated, [key]].value_counts().head(10)
        raise ValueError(
            f"{label} must contain at most one row per {key!r}. "
            f"Duplicate sample:\n{sample.to_string()}"
        )


def write_parquet_table(df: pd.DataFrame, path: Path) -> None:
    """Write dataframe values without serializing custom dataframe attributes."""
    export = df.copy()
    export.attrs = {}
    export.to_parquet(path, index=False)


def select_and_order_columns(
    df: pd.DataFrame,
    columns: Sequence[str],
) -> pd.DataFrame:
    """Keep exactly the requested columns in the requested order."""
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise KeyError(f"Selected final columns are missing from the table: {missing}")
    return df.loc[:, list(columns)].copy()


def normalize_identifier(value: Any, width: int | None) -> Any:
    """Normalize an identifier while preserving missing values."""
    if pd.isna(value):
        return pd.NA
    if isinstance(value, str):
        text = value.strip()
    elif isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        text = str(int(value))
    elif isinstance(value, (float, np.floating)) and not isinstance(value, bool):
        if not np.isfinite(float(value)):
            return pd.NA
        text = str(int(value)) if float(value).is_integer() else format(float(value), "g")
    else:
        text = str(value).strip()

    if not text:
        return pd.NA
    return text.zfill(width) if width is not None and len(text) < width else text


def normalize_identifier_series(
    series: pd.Series,
    width: int | None,
) -> pd.Series:
    """Normalize a complete identifier series."""
    return series.map(lambda value: normalize_identifier(value, width)).astype("string")


def collect_in_scope_business_identifiers(
    finess_df: pd.DataFrame,
    dataset1_df: pd.DataFrame,
    dataset2_df: pd.DataFrame,
    *,
    entity_column: str,
    business_id_column: str,
) -> list[str]:
    """Return business identifiers that can become proposals for in-scope FINESS rows."""
    entity_keys = set(finess_df[entity_column].dropna().astype("string"))
    candidate_series = [finess_df[business_id_column]]

    for source in (dataset1_df, dataset2_df):
        if entity_column not in source.columns or business_id_column not in source.columns:
            raise KeyError(
                f"Source table must contain {entity_column!r} and "
                f"{business_id_column!r}."
            )
        candidate_series.append(
            source.loc[
                source[entity_column].astype("string").isin(entity_keys),
                business_id_column,
            ]
        )

    values = pd.concat(candidate_series, ignore_index=True).astype("string")
    values = values.str.strip().replace({"": pd.NA, "N/A": pd.NA, "NA": pd.NA})
    return sorted(values.dropna().drop_duplicates().tolist())


def nonempty_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def join_nonempty(values: Iterable[Any], separator: str = " ") -> str:
    parts = [nonempty_text(value) for value in values]
    return separator.join(part for part in parts if part)


def format_naf_code(series: pd.Series) -> pd.Series:
    """Normalize 6619A-like and 66.19A-like values to 66.19A."""
    normalized = (
        series.astype("string")
        .str.strip()
        .str.upper()
        .str.replace(" ", "", regex=False)
    )
    return normalized.str.replace(
        r"^(\d{2})(\d{2})([A-Z])$",
        r"\1.\2\3",
        regex=True,
    )


def normalize_integer_code(series: pd.Series) -> pd.Series:
    """Normalize Excel-style integer codes such as 1000 and 1000.0."""
    return series.astype("string").str.strip().str.replace(r"\.0$", "", regex=True)


def load_lookup_series(
    path: Path,
    *,
    code_column: str,
    label_column: str,
    formatter=None,
) -> pd.Series:
    """Load a small reference workbook as one normalized code-to-label series."""
    lookup = pd.read_excel(path, dtype="string")
    missing = {code_column, label_column} - set(lookup.columns)
    if missing:
        raise KeyError(f"Missing lookup columns: {sorted(missing)}")

    lookup = lookup.loc[
        lookup[code_column].notna(),
        [code_column, label_column],
    ].copy()
    if formatter is not None:
        lookup[code_column] = formatter(lookup[code_column])
    lookup = lookup.drop_duplicates(subset=[code_column], keep="first")
    return lookup.set_index(code_column)[label_column]


def validate_proposal_output(
    enriched_table: pd.DataFrame,
    proposal_table: pd.DataFrame,
    *,
    entity_column: str,
    proposal_column: str,
    initial_flag_column: str,
) -> None:
    """Validate entity and proposal invariants relied on by downstream stages."""
    assert_unique_key(enriched_table, entity_column, "Enriched consistency table")

    duplicates = proposal_table.duplicated(
        subset=[entity_column, proposal_column],
        keep=False,
    )
    if duplicates.any():
        sample = proposal_table.loc[
            duplicates,
            [entity_column, proposal_column, "candidate_rank"],
        ].head(20)
        raise ValueError(
            f"Duplicate ({entity_column}, {proposal_column}) rows found. Sample:\n"
            f"{sample.to_string(index=False)}"
        )

    initial_counts = proposal_table.groupby(entity_column, dropna=False)[
        initial_flag_column
    ].sum()
    if not initial_counts.eq(1).all():
        sample = initial_counts.loc[~initial_counts.eq(1)].head(20)
        raise ValueError(
            f"Each {entity_column} must have exactly one initial proposal row. "
            f"Sample:\n{sample.to_string()}"
        )

    rank_minimums = proposal_table.groupby(entity_column, dropna=False)[
        "candidate_rank"
    ].min()
    if not rank_minimums.eq(1).all():
        raise ValueError(f"candidate_rank must start at 1 for every {entity_column}.")
