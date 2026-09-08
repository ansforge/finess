"""Preparation jobs for the June 2026 Adrien Tortel proposal extracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

ADRIEN_SOURCE_FLAG_COLUMNS = [
    "source_siret_prop_claire",
    "source_siret_prop_dsn",
    "source_siret_prop_elargissement_siren",
    "source_siret_prop_elargissement_siren_claire_lelarge",
    "source_siret_prop_insee",
    "source_siret_prop_jean_claude_gpt_ech",
    "source_siret_prop_lien_de_succession_direct",
    "source_siret_prop_lien_de_succession_indirect",
    "source_siret_prop_referentiel_interne",
]

ADRIEN_EGE_KEYS = ["nofinesset", "siret_prop"]
ADRIEN_EGE_RESOLVED_CONFLICT_COLUMNS = [
    "score_denomination_prop",
    *ADRIEN_SOURCE_FLAG_COLUMNS,
    "source_siret_prop_nb",
]


def prepare_adrien_candidates(
    initial_path: Path, proposal_path: Path
) -> pd.DataFrame:
    """Select lexically concordant rows and standardize initial/proposal fields."""
    initial = pd.read_parquet(initial_path)
    proposals = pd.read_parquet(proposal_path)

    if "concordance_lexicographique_init" not in initial:
        raise ValueError(f"{initial_path}: missing concordance_lexicographique_init")
    if "concordance_lexicographique_prop" not in proposals:
        raise ValueError(f"{proposal_path}: missing concordance_lexicographique_prop")

    initial = initial.loc[initial["concordance_lexicographique_init"].eq(True)].copy()
    proposals = proposals.loc[
        proposals["concordance_lexicographique_prop"].eq(True)
    ].copy()

    for column in [name for name in initial.columns if name.endswith("_init")]:
        standardized = column.removesuffix("_init") + "_prop"
        if standardized not in initial:
            initial[standardized] = initial[column]

    initial["step"] = 1
    proposals["step"] = 2
    result = pd.concat([initial, proposals], ignore_index=True, sort=False)
    result = result.loc[:, [name for name in result.columns if name != "step"] + ["step"]]

    utc_columns = result.select_dtypes(include=["datetime64[ns, UTC]"]).columns
    for column in utc_columns:
        result[column] = result[column].dt.date
    return result


def _conflict_counts(
    source: pd.DataFrame, keys: list[str], columns: list[str]
) -> dict[str, int]:
    duplicate_rows = source.loc[source.duplicated(keys, keep=False)]
    if duplicate_rows.empty:
        return {}
    grouped = duplicate_rows.groupby(keys, sort=False, dropna=False)
    return {
        column: int((grouped[column].nunique(dropna=False) > 1).sum())
        for column in columns
        if (grouped[column].nunique(dropna=False) > 1).any()
    }


def resolve_adrien_ege_duplicates(
    source: pd.DataFrame,
    *,
    additional_source_flag_columns: tuple[str, ...] = (),
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Resolve one FINESS-EGE/SIRET pair using explicit evidence union rules.

    Every field outside the allow-listed evidence columns must be identical within
    a duplicate key. Denomination score uses the maximum observed score, source
    flags use logical OR, and the source count is recomputed from those unioned
    flags. Additional source flags can be declared explicitly for experimental
    variants without changing the canonical Adrien source definition.
    """
    source_flag_columns = [
        *ADRIEN_SOURCE_FLAG_COLUMNS,
        *additional_source_flag_columns,
    ]
    resolved_conflict_columns = [
        *ADRIEN_EGE_RESOLVED_CONFLICT_COLUMNS,
        *additional_source_flag_columns,
    ]

    missing = set(ADRIEN_EGE_KEYS + resolved_conflict_columns) - set(source.columns)
    if missing:
        raise ValueError(f"Adrien EGE columns missing: {sorted(missing)}")

    duplicate_mask = source.duplicated(ADRIEN_EGE_KEYS, keep=False)
    duplicate_rows = source.loc[duplicate_mask].copy()
    duplicate_group_count = (
        duplicate_rows.groupby(ADRIEN_EGE_KEYS, sort=False, dropna=False).ngroups
        if not duplicate_rows.empty
        else 0
    )
    invariant_columns = [
        column
        for column in source.columns
        if column not in ADRIEN_EGE_KEYS + resolved_conflict_columns
    ]
    invariant_conflicts = _conflict_counts(source, ADRIEN_EGE_KEYS, invariant_columns)
    if invariant_conflicts:
        raise ValueError(
            "Adrien EGE duplicate groups conflict outside the documented "
            f"evidence fields: {invariant_conflicts}"
        )

    evidence_conflicts = _conflict_counts(
        source, ADRIEN_EGE_KEYS, resolved_conflict_columns
    )
    if duplicate_rows.empty:
        return source.copy(), {
            "input_rows": len(source),
            "output_rows": len(source),
            "duplicate_groups": 0,
            "evidence_conflicts": {},
        }

    grouped = duplicate_rows.groupby(ADRIEN_EGE_KEYS, sort=False, dropna=False)
    resolved = grouped.head(1).copy()
    resolved_index = pd.MultiIndex.from_frame(resolved[ADRIEN_EGE_KEYS])

    max_scores = grouped["score_denomination_prop"].max()
    resolved["score_denomination_prop"] = max_scores.loc[resolved_index].to_numpy()

    for column in source_flag_columns:
        unioned = grouped[column].any()
        resolved[column] = unioned.loc[resolved_index].to_numpy()
    resolved["source_siret_prop_nb"] = (
        resolved[source_flag_columns]
        .fillna(False)
        .astype(bool)
        .sum(axis=1)
        .astype(float)
    )

    result = pd.concat([source.loc[~duplicate_mask], resolved], axis=0).sort_index()
    result = result.reset_index(drop=True)
    if result.duplicated(ADRIEN_EGE_KEYS).any():
        raise ValueError("Adrien EGE duplicate resolution left duplicate keys")
    return result, {
        "input_rows": len(source),
        "output_rows": len(result),
        "rows_removed": len(source) - len(result),
        "duplicate_groups": duplicate_group_count,
        "evidence_conflicts": evidence_conflicts,
        "rule": "max denomination score; OR source flags; recompute source count",
    }


def prepare_adrien_ej(source: pd.DataFrame) -> pd.DataFrame:
    """Aggregate June candidates to explicit FINESS-EJ/SIREN metrics."""
    keys = ["nofinessej", "siren_prop"]
    mean_columns = {
        "score_denomination_siret_avg": "score_denomination_prop",
        "score_adresse_siret_avg": "score_adresse_prop",
        "source_siret_claire_avg": "source_siret_prop_claire",
        "source_siret_dsn_avg": "source_siret_prop_dsn",
        "source_siret_elargissement_siren_avg": "source_siret_prop_elargissement_siren",
        "source_siret_elargissement_siren_claire_lelarge_avg": "source_siret_prop_elargissement_siren_claire_lelarge",
        "source_siret_insee_avg": "source_siret_prop_insee",
        "source_siret_jean_claude_gpt_ech_avg": "source_siret_prop_jean_claude_gpt_ech",
        "source_siret_lien_de_succession_direct_avg": "source_siret_prop_lien_de_succession_direct",
        "source_siret_lien_de_succession_indirect_avg": "source_siret_prop_lien_de_succession_indirect",
        "source_siret_referentiel_interne_avg": "source_siret_prop_referentiel_interne",
        "source_siret_nb_avg": "source_siret_prop_nb",
    }
    required = set(keys + ["step", *mean_columns.values()])
    missing = required - set(source.columns)
    if missing:
        raise ValueError(f"Adrien EJ columns missing: {sorted(missing)}")

    grouped = source.groupby(keys, sort=False, dropna=False)
    result = grouped.size().rename("ej_siren_pair_count").reset_index()
    source_index = source.set_index(keys).index
    for output_name, input_name in mean_columns.items():
        values = pd.Series(source[input_name].to_numpy(), index=source_index)
        result[output_name] = (
            values.groupby(level=[0, 1], sort=False).mean().to_numpy()
        )
    for step in (1, 2):
        values = pd.Series(source["step"].eq(step).to_numpy(), index=source_index)
        result[f"step_{step}_siret_count"] = (
            values.groupby(level=[0, 1], sort=False).sum().to_numpy()
        )

    result["ej_total_rows"] = result.groupby("nofinessej", sort=False)[
        "ej_siren_pair_count"
    ].transform("sum")
    result["pair_share_within_ej"] = (
        result["ej_siren_pair_count"] / result["ej_total_rows"]
    )
    if result.duplicated(keys).any():
        raise ValueError("Adrien EJ aggregation left duplicate EJ/SIREN pairs")
    return result


def duplicate_rule_examples() -> pd.DataFrame:
    """Run two tiny examples that make the duplicate policy inspectable."""
    base = {
        "nofinesset": "010000001",
        "siret_prop": "11111111111111",
        "score_denomination_prop": 0.4,
        "source_siret_prop_nb": 1.0,
    }
    for column in ADRIEN_SOURCE_FLAG_COLUMNS:
        base[column] = False
    first = dict(base)
    first[ADRIEN_SOURCE_FLAG_COLUMNS[0]] = True
    second = dict(base)
    second["score_denomination_prop"] = 0.8
    second[ADRIEN_SOURCE_FLAG_COLUMNS[1]] = True
    identical_first = dict(first)
    identical_first["nofinesset"] = "010000002"
    identical_first["siret_prop"] = "22222222222222"
    identical_second = dict(identical_first)
    source = pd.DataFrame([first, second, identical_first, identical_second])
    resolved, _ = resolve_adrien_ege_duplicates(source)
    conflicting_row = resolved.loc[resolved["nofinesset"].eq("010000001")].iloc[0]
    identical_row = resolved.loc[resolved["nofinesset"].eq("010000002")].iloc[0]
    return pd.DataFrame(
        [
            {
                "example": "conflicting evidence",
                "input_rows": 2,
                "output_rows": 1,
                "expected": "max score 0.8; two unioned sources",
                "observed": (
                    f"max score {conflicting_row['score_denomination_prop']}; "
                    f"{int(conflicting_row['source_siret_prop_nb'])} unioned sources"
                ),
                "passed": bool(
                    conflicting_row["score_denomination_prop"] == 0.8
                    and conflicting_row["source_siret_prop_nb"] == 2
                ),
            },
            {
                "example": "identical duplicate",
                "input_rows": 2,
                "output_rows": 1,
                "expected": "same score 0.4; one source",
                "observed": (
                    f"same score {identical_row['score_denomination_prop']}; "
                    f"{int(identical_row['source_siret_prop_nb'])} source"
                ),
                "passed": bool(
                    identical_row["score_denomination_prop"] == 0.4
                    and identical_row["source_siret_prop_nb"] == 1
                ),
            },
        ]
    )
