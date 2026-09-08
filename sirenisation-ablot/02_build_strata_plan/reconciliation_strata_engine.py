"""Neutral reconciliation strata planning and reviewer assignment.

The engine supports multiple reconciliation levels through configuration, for
example:

- EJ <-> SIREN (legal-entity reconciliation)
- EGE <-> SIRET (establishment reconciliation)

User-facing identifier columns are normalized at the module boundary to the
canonical internal names ``entity_id`` and ``business_id``.  The core logic
therefore does not depend on EJ, EGE, SIREN, SIRET, or any other domain label.

Typical use
-----------

>>> names = ReconciliationNames.ege_siret()
>>> canonical = prepare_reconciliation_table(proposals, names)
>>> result = build_strata_from_variables(
...     proposals,
...     ["country", "activity"],
...     names=names,
... )
>>> reviewer_result = assign_reviewers_round_robin(
...     result.strata_plan,
...     ["reviewer_a", "reviewer_b"],
... )

For legal-entity reconciliation, only the configuration changes:

>>> names = ReconciliationNames.ej_siren(entity_pad_width=9)
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import blake2b
from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ENTITY_ID = "entity_id"
BUSINESS_ID = "business_id"
ENTITY_COUNT = "n_entity"
DEFAULT_EGE_PAD_WIDTH = 9
DEFAULT_SIREN_PAD_WIDTH = 9
DEFAULT_SIRET_PAD_WIDTH = 14
MISSING_LEVEL = "<NA>"
UNASSIGNED_REVIEWER = "<UNASSIGNED>"


@dataclass(frozen=True)
class ReconciliationNames:
    """Map user-facing reconciliation names to neutral internal names.

    Parameters
    ----------
    entity:
        Human-readable name for the left side of the reconciliation, such as
        ``"EJ"`` or ``"EGE"``.
    business:
        Human-readable name for the right side, such as ``"SIREN"`` or
        ``"SIRET"``.
    entity_id_column, business_id_column:
        Column names used in user-provided tables.
    entity_pad_width, business_pad_width:
        Optional zero-padding widths applied during identifier normalization.
        Use ``None`` when leading-zero padding is not appropriate.
    """

    entity: str = "entity"
    business: str = "business"
    entity_id_column: str = ENTITY_ID
    business_id_column: str = BUSINESS_ID
    entity_pad_width: int | None = None
    business_pad_width: int | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "entity",
            "business",
            "entity_id_column",
            "business_id_column",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string.")
        if self.entity_id_column == self.business_id_column:
            raise ValueError(
                "entity_id_column and business_id_column must be different."
            )
        for field_name in ("entity_pad_width", "business_pad_width"):
            width = getattr(self, field_name)
            if width is not None and width < 1:
                raise ValueError(f"{field_name} must be positive or None.")

    @classmethod
    def neutral(cls) -> ReconciliationNames:
        """Configuration for tables already using canonical column names."""
        return cls()

    @classmethod
    def ej_siren(
        cls,
        *,
        entity_id_column: str = "EJ",
        business_id_column: str = "SIREN",
        entity_pad_width: int | None = None,
        business_pad_width: int | None = DEFAULT_SIREN_PAD_WIDTH,
    ) -> ReconciliationNames:
        """Configuration for legal-entity EJ <-> SIREN reconciliation."""
        return cls(
            entity="EJ",
            business="SIREN",
            entity_id_column=entity_id_column,
            business_id_column=business_id_column,
            entity_pad_width=entity_pad_width,
            business_pad_width=business_pad_width,
        )

    @classmethod
    def ege_siret(
        cls,
        *,
        entity_id_column: str = "EGE",
        business_id_column: str = "SIRET",
        entity_pad_width: int | None = DEFAULT_EGE_PAD_WIDTH,
        business_pad_width: int | None = DEFAULT_SIRET_PAD_WIDTH,
    ) -> ReconciliationNames:
        """Configuration for establishment EGE <-> SIRET reconciliation."""
        return cls(
            entity="EGE",
            business="SIRET",
            entity_id_column=entity_id_column,
            business_id_column=business_id_column,
            entity_pad_width=entity_pad_width,
            business_pad_width=business_pad_width,
        )

    @property
    def user_entity_count_column(self) -> str:
        """Return the user-facing count name, for example ``n_EGE``."""
        return f"n_{self.entity}"


@dataclass
class ReconciliationTableResult:
    """Canonical reconciliation table plus basic identifier diagnostics."""

    table: pd.DataFrame
    duplicate_pairs: pd.DataFrame
    missing_entity_rows: pd.DataFrame
    missing_business_rows: pd.DataFrame
    names: ReconciliationNames


@dataclass
class StrataPlanResult:
    """Outputs produced by entity-level stratification."""

    entity_assignments: pd.DataFrame
    strata_plan: pd.DataFrame
    stratum_codebook: pd.DataFrame
    stratification_variables: list[str]
    level_mapping: pd.DataFrame
    inconsistent_entity_values: pd.DataFrame
    missing_entity_assignments: pd.DataFrame
    names: ReconciliationNames


@dataclass
class ReviewerPlanResult:
    """Stratum-to-reviewer assignment outputs."""

    strata_plan: pd.DataFrame
    reviewer_statistics: pd.DataFrame
    missing_reviewer_assignments: pd.DataFrame


@dataclass
class SampleSizePlanResult:
    """Final review plan after merging manually entered sample sizes."""

    strata_plan: pd.DataFrame
    sample_size_input: pd.DataFrame
    reviewer_statistics: pd.DataFrame


def load_table(path: str | Path, *, sheet_name: int | str = 0) -> pd.DataFrame:
    """Load a Parquet or Excel table."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, sheet_name=sheet_name, dtype="string")
    raise ValueError(
        f"Unsupported file format for {path.name!r}: expected Parquet or Excel."
    )


def _normalize_identifier(value: Any, width: int | None) -> Any:
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
    *,
    pad_to_length: int | None = None,
) -> pd.Series:
    """Normalize identifiers as strings while preserving leading zeros."""
    return series.map(
        lambda value: _normalize_identifier(value, pad_to_length)
    ).astype("string")


def _require_columns(df: pd.DataFrame, columns: Sequence[str], label: str) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise KeyError(f"Missing columns in {label}: {missing}")


def _validate_canonicalization_collisions(
    df: pd.DataFrame,
    names: ReconciliationNames,
    *,
    include_business: bool,
) -> None:
    source_columns = {names.entity_id_column}
    canonical_targets = {ENTITY_ID}
    if include_business:
        source_columns.add(names.business_id_column)
        canonical_targets.add(BUSINESS_ID)

    collisions = sorted(
        column
        for column in canonical_targets
        if column in df.columns and column not in source_columns
    )
    if collisions:
        raise ValueError(
            "Cannot create canonical identifier columns because the input already "
            f"contains unrelated column(s): {collisions}. Rename them first."
        )


def _canonicalize_identifier_columns(
    df: pd.DataFrame,
    names: ReconciliationNames,
    *,
    include_business: bool,
) -> pd.DataFrame:
    required = [names.entity_id_column]
    if include_business:
        required.append(names.business_id_column)
    _require_columns(df, required, "input table")
    _validate_canonicalization_collisions(
        df,
        names,
        include_business=include_business,
    )

    rename_map = {names.entity_id_column: ENTITY_ID}
    if include_business:
        rename_map[names.business_id_column] = BUSINESS_ID

    work = df.copy().rename(columns=rename_map)
    work[ENTITY_ID] = normalize_identifier_series(
        work[ENTITY_ID], pad_to_length=names.entity_pad_width
    )
    if include_business:
        work[BUSINESS_ID] = normalize_identifier_series(
            work[BUSINESS_ID], pad_to_length=names.business_pad_width
        )
    return work


def prepare_reconciliation_table(
    df: pd.DataFrame,
    names: ReconciliationNames | None = None,
    *,
    require_entity_id: bool = True,
    require_business_id: bool = True,
) -> ReconciliationTableResult:
    """Convert a user table to the canonical entity/business representation.

    The returned table always uses ``entity_id`` and ``business_id``. Duplicate
    pairs are reported but retained because proposal tables may legitimately
    carry repeated rows with different metadata.
    """
    names = names or ReconciliationNames.neutral()
    work = _canonicalize_identifier_columns(df, names, include_business=True)

    missing_entity = work.loc[work[ENTITY_ID].isna()].copy()
    missing_business = work.loc[work[BUSINESS_ID].isna()].copy()
    if require_entity_id and not missing_entity.empty:
        raise ValueError(
            f"The input table contains {len(missing_entity):,} row(s) with a "
            f"missing {names.entity} identifier."
        )
    if require_business_id and not missing_business.empty:
        raise ValueError(
            f"The input table contains {len(missing_business):,} row(s) with a "
            f"missing {names.business} identifier."
        )

    duplicate_mask = work.duplicated([ENTITY_ID, BUSINESS_ID], keep=False)
    duplicate_pairs = (
        work.loc[duplicate_mask, [ENTITY_ID, BUSINESS_ID]]
        .value_counts(dropna=False)
        .rename("n_rows")
        .reset_index()
        .sort_values([ENTITY_ID, BUSINESS_ID], kind="stable")
        .reset_index(drop=True)
    )

    return ReconciliationTableResult(
        table=work,
        duplicate_pairs=duplicate_pairs,
        missing_entity_rows=missing_entity,
        missing_business_rows=missing_business,
        names=names,
    )


def to_user_columns(
    df: pd.DataFrame,
    names: ReconciliationNames,
    *,
    rename_entity_count: bool = True,
) -> pd.DataFrame:
    """Return a copy with canonical columns renamed for user-facing output."""
    rename_map: dict[str, str] = {}
    if ENTITY_ID in df.columns:
        rename_map[ENTITY_ID] = names.entity_id_column
    if BUSINESS_ID in df.columns:
        rename_map[BUSINESS_ID] = names.business_id_column
    if rename_entity_count and ENTITY_COUNT in df.columns:
        rename_map[ENTITY_COUNT] = names.user_entity_count_column
    return df.rename(columns=rename_map).copy()


def _display_value(value: Any) -> str:
    return MISSING_LEVEL if pd.isna(value) else str(value)


def find_inconsistent_group_values(
    df: pd.DataFrame,
    *,
    group_column: str,
    columns: Sequence[str],
) -> pd.DataFrame:
    """Return values that vary within a group expected to be constant."""
    columns = list(dict.fromkeys(columns))
    _require_columns(df, [group_column, *columns], "table")
    output_columns = [group_column, "variable", "n_distinct_values", "values"]
    if not columns or df.empty:
        return pd.DataFrame(columns=output_columns)

    counts = df.groupby(group_column, sort=False, dropna=False)[columns].nunique(
        dropna=False
    )
    problematic = counts.stack()
    problematic = problematic.loc[problematic > 1]

    rows: list[dict[str, Any]] = []
    for (group_value, variable), n_values in problematic.items():
        if pd.isna(group_value):
            group_mask = df[group_column].isna()
        else:
            group_mask = df[group_column].eq(group_value)
        values = df.loc[group_mask, variable].drop_duplicates().tolist()
        rows.append(
            {
                group_column: group_value,
                "variable": variable,
                "n_distinct_values": int(n_values),
                "values": tuple(_display_value(value) for value in values),
            }
        )
    return pd.DataFrame(rows, columns=output_columns)


def find_inconsistent_entity_values(
    df: pd.DataFrame,
    columns: Sequence[str],
    *,
    names: ReconciliationNames | None = None,
) -> pd.DataFrame:
    """Check that selected variables have exactly one value per entity."""
    names = names or ReconciliationNames.neutral()
    columns = list(dict.fromkeys(columns))
    _require_columns(df, [names.entity_id_column, *columns], "input table")

    selected = df.loc[:, [names.entity_id_column, *columns]].copy()
    work = _canonicalize_identifier_columns(
        selected,
        names,
        include_business=False,
    )
    if work[ENTITY_ID].isna().any():
        raise ValueError(
            f"The input table contains missing {names.entity} identifiers."
        )
    return find_inconsistent_group_values(
        work,
        group_column=ENTITY_ID,
        columns=columns,
    )


def _collapse_to_entity(
    df: pd.DataFrame,
    columns: Sequence[str],
    *,
    names: ReconciliationNames,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    issues = find_inconsistent_entity_values(df, columns, names=names)
    if not issues.empty:
        raise ValueError(
            f"Selected {names.entity}-level columns are not constant within every "
            f"{names.entity}. Found {len(issues):,} issue(s). Sample:\n"
            f"{issues.head(10).to_string(index=False)}"
        )

    selected = df.loc[:, [names.entity_id_column, *columns]].copy()
    work = _canonicalize_identifier_columns(
        selected,
        names,
        include_business=False,
    )
    work = (
        work.drop_duplicates(subset=[ENTITY_ID], keep="first")
        .reset_index(drop=True)
    )
    return work, issues


def _normalize_level(value: Any) -> Any:
    """Normalize stratification levels to their stable codebook representation."""
    if pd.isna(value):
        return MISSING_LEVEL
    if isinstance(value, (bool, np.bool_)):
        return "True" if bool(value) else "False"
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return int(value) if float(value).is_integer() else float(value)
    return value


def _explicit_order_map(
    order: Sequence[Any] | Mapping[Any, int] | None,
) -> dict[Any, int]:
    """Return normalized fixed level IDs for an explicit variable order.

    When an explicit order is supplied, its ranks are authoritative: levels keep
    the same component IDs even when some of them are absent from the current
    dataframe. Missing values normalize to ``MISSING_LEVEL`` (``"<NA>"``).
    """
    if order is None:
        return {}

    items = order.items() if isinstance(order, Mapping) else zip(order, range(len(order)))
    result: dict[Any, int] = {}
    used_ranks: set[int] = set()
    for value, rank in items:
        normalized_value = _normalize_level(value)
        normalized_rank = int(rank)
        if normalized_rank < 0:
            raise ValueError("Explicit variable-order ranks must be non-negative.")
        if normalized_value in result:
            raise ValueError("Duplicate values in an explicit variable order.")
        if normalized_rank in used_ranks:
            raise ValueError("Duplicate ranks in an explicit variable order.")
        result[normalized_value] = normalized_rank
        used_ranks.add(normalized_rank)
    return result


def _build_strata_plan(
    entity_assignments: pd.DataFrame,
    variables: Sequence[str],
) -> pd.DataFrame:
    assigned = entity_assignments.loc[
        entity_assignments["stratum_id"].notna()
    ].copy()
    group_columns = ["stratum_id", *variables]
    if assigned.empty:
        return pd.DataFrame(columns=[*group_columns, ENTITY_COUNT])
    plan = (
        assigned.groupby(group_columns, dropna=False, sort=False)
        .agg(**{ENTITY_COUNT: (ENTITY_ID, "nunique")})
        .reset_index()
        .sort_values("stratum_id", kind="stable")
        .reset_index(drop=True)
    )
    plan[ENTITY_COUNT] = plan[ENTITY_COUNT].astype("int64")
    return plan



def _build_theoretical_codebook(
    level_mapping: pd.DataFrame,
    variables: Sequence[str],
) -> pd.DataFrame:
    """Build the full Cartesian codebook from the coding levels just created."""
    required = {"variable", "value", "level_id", "stratum_component"}
    missing = required.difference(level_mapping.columns)
    if missing:
        raise KeyError(
            "The coding level mapping is missing required columns: "
            f"{sorted(missing)}"
        )

    levels_by_variable: list[list[dict[str, Any]]] = []
    for variable in variables:
        levels = level_mapping.loc[level_mapping["variable"].eq(variable)].copy()
        if levels.empty:
            raise ValueError(f"No coding levels are available for {variable!r}.")
        levels = levels.sort_values(
            ["level_id", "stratum_component"],
            kind="stable",
        )
        if levels["level_id"].duplicated().any():
            raise ValueError(f"Duplicate coding level IDs for {variable!r}.")
        levels_by_variable.append(
            levels.loc[:, ["value", "stratum_component"]].to_dict("records")
        )

    rows: list[dict[str, Any]] = []
    for combination in product(*levels_by_variable):
        row: dict[str, Any] = {
            "stratum_id": "".join(
                str(level["stratum_component"]) for level in combination
            )
        }
        for variable, level in zip(variables, combination, strict=True):
            row[variable] = level["value"]
        rows.append(row)

    codebook = pd.DataFrame(rows, columns=["stratum_id", *variables])
    for column in codebook.columns:
        codebook[column] = codebook[column].astype("string")
    return codebook.sort_values("stratum_id", kind="stable").reset_index(drop=True)


def _build_mapping_codebook(
    mapping: pd.DataFrame,
    variables: Sequence[str],
) -> pd.DataFrame:
    """Build one codebook row for every stratum present in the complete mapping."""
    columns = ["stratum_id", *variables]
    _require_columns(mapping, columns, "entity-to-stratum mapping")

    work = mapping.loc[:, columns].copy()
    work["stratum_id"] = (
        work["stratum_id"].astype("string").str.strip().replace("", pd.NA)
    )
    if work["stratum_id"].isna().any():
        raise ValueError(
            "The entity-to-stratum mapping contains missing stratum_id values."
        )

    for variable in variables:
        work[variable] = work[variable].map(_normalize_level)

    issues = find_inconsistent_group_values(
        work,
        group_column="stratum_id",
        columns=variables,
    )
    if not issues.empty:
        raise ValueError(
            "The entity-to-stratum mapping defines conflicting values within a "
            f"stratum. Sample:\n{issues.head(10).to_string(index=False)}"
        )

    codebook = work.drop_duplicates(subset=["stratum_id"], keep="first")
    codebook = codebook.sort_values("stratum_id", kind="stable").reset_index(drop=True)
    for column in codebook.columns:
        codebook[column] = codebook[column].astype("string")
    return codebook


def build_strata_from_variables(
    df: pd.DataFrame,
    stratification_variables: Sequence[str],
    *,
    names: ReconciliationNames | None = None,
    variable_orders: Mapping[str, Sequence[Any] | Mapping[Any, int]] | None = None,
) -> StrataPlanResult:
    """Create deterministic stratum IDs from selected entity-level variables.

    With an explicit order, the declared domain is authoritative: every declared
    level keeps its fixed component ID even when absent from the current data,
    and observed values outside that domain are rejected. Missing values are a
    real categorical level represented by ``MISSING_LEVEL`` (``"<NA>"``).

    Without an explicit order, levels are inferred from the observed data as in
    the generic engine behavior. Components are concatenated in variable order.
    """
    names = names or ReconciliationNames.neutral()
    variables = list(dict.fromkeys(stratification_variables))
    if not variables:
        raise ValueError("Select at least one stratification variable.")

    variable_orders = variable_orders or {}
    entity_table, issues = _collapse_to_entity(
        df,
        variables,
        names=names,
    )

    components: list[pd.Series] = []
    level_rows: list[dict[str, Any]] = []
    for position, variable in enumerate(variables, start=1):
        normalized = entity_table[variable].map(_normalize_level)
        # The stratification products expose missingness as the explicit category
        # ``<NA>`` rather than as dataframe nulls.
        entity_table[variable] = normalized

        explicit_spec = variable_orders.get(variable)
        order_map = _explicit_order_map(explicit_spec)

        if explicit_spec is not None:
            observed_values = normalized.drop_duplicates().tolist()
            unknown_values = [
                value for value in observed_values if value not in order_map
            ]
            if unknown_values:
                raise ValueError(
                    f"Observed values for {variable!r} are absent from its explicit "
                    f"order: {unknown_values}"
                )

            ordered_levels = sorted(
                order_map,
                key=lambda value: (order_map[value], str(value)),
            )
            value_to_id = dict(order_map)
            max_level_id = max(value_to_id.values(), default=0)
        else:
            levels = pd.DataFrame({"value": normalized.drop_duplicates().tolist()})
            levels["_order"] = levels["value"].map(
                lambda value: (value == MISSING_LEVEL, str(value))
            )
            ordered_levels = (
                levels.sort_values("_order", kind="stable")["value"].tolist()
            )
            value_to_id = {
                value: index for index, value in enumerate(ordered_levels)
            }
            max_level_id = max(value_to_id.values(), default=0)

        width = max(1, len(str(max_level_id)))
        component = normalized.map(value_to_id).map(
            lambda value, width=width: str(int(value)).zfill(width)
        )
        components.append(component)

        counts = normalized.value_counts(dropna=False)
        for value in ordered_levels:
            level_id = value_to_id[value]
            level_rows.append(
                {
                    "variable_position": position,
                    "variable": variable,
                    "value": value,
                    "level_id": level_id,
                    "stratum_component": str(level_id).zfill(width),
                    ENTITY_COUNT: int(counts.get(value, 0)),
                }
            )

    stratum_id = components[0].astype("string")
    for component in components[1:]:
        stratum_id = stratum_id + component.astype("string")

    assignments = entity_table.copy()
    assignments.insert(1, "stratum_id", stratum_id)
    plan = _build_strata_plan(assignments, variables)
    level_mapping = pd.DataFrame(level_rows)
    codebook = _build_theoretical_codebook(level_mapping, variables)

    return StrataPlanResult(
        entity_assignments=assignments,
        strata_plan=plan,
        stratum_codebook=codebook,
        stratification_variables=variables,
        level_mapping=level_mapping,
        inconsistent_entity_values=issues,
        missing_entity_assignments=pd.DataFrame(columns=assignments.columns),
        names=names,
    )


def load_entity_strata_mapping(
    df: pd.DataFrame,
    mapping_df: pd.DataFrame,
    *,
    names: ReconciliationNames | None = None,
    mapping_entity_id_column: str | None = None,
    mapping_stratum_column: str = "stratum_id",
    additional_columns: Sequence[str] | None = None,
) -> StrataPlanResult:
    """Attach an external mapping and derive its complete stratum codebook.

    ``additional_columns`` describe the mapped strata. The codebook is built from
    the complete mapping before it is restricted to entities present in ``df``;
    therefore every stratum supplied in the mapping is retained.
    """
    names = names or ReconciliationNames.neutral()
    variables = list(dict.fromkeys(additional_columns or []))
    source_entity, _ = _collapse_to_entity(df, [], names=names)

    mapping_entity_id_column = (
        mapping_entity_id_column or names.entity_id_column
    )
    mapping_columns = [mapping_stratum_column, *variables]
    _require_columns(
        mapping_df,
        [mapping_entity_id_column, *mapping_columns],
        "entity-to-stratum mapping",
    )

    mapping_names = ReconciliationNames(
        entity=names.entity,
        business=names.business,
        entity_id_column=mapping_entity_id_column,
        business_id_column=names.business_id_column,
        entity_pad_width=names.entity_pad_width,
        business_pad_width=names.business_pad_width,
    )
    mapping_selected = mapping_df.loc[
        :, [mapping_entity_id_column, *mapping_columns]
    ].copy()

    mapping_issues = find_inconsistent_entity_values(
        mapping_selected,
        mapping_columns,
        names=mapping_names,
    )
    if not mapping_issues.empty:
        raise ValueError(
            "The entity-to-stratum mapping has conflicting rows. Sample:\n"
            f"{mapping_issues.head(10).to_string(index=False)}"
        )

    mapping = _canonicalize_identifier_columns(
        mapping_selected,
        mapping_names,
        include_business=False,
    )
    if mapping[ENTITY_ID].isna().any():
        raise ValueError(
            "The entity-to-stratum mapping contains missing entity identifiers."
        )

    mapping = mapping.rename(columns={mapping_stratum_column: "stratum_id"})
    mapping["stratum_id"] = (
        mapping["stratum_id"].astype("string").str.strip().replace("", pd.NA)
    )
    if mapping["stratum_id"].isna().any():
        raise ValueError(
            "The entity-to-stratum mapping contains missing stratum_id values."
        )

    for variable in variables:
        mapping[variable] = mapping[variable].map(_normalize_level)

    codebook = _build_mapping_codebook(mapping, variables)

    mapping = mapping.drop_duplicates(ENTITY_ID, keep="first")
    assignments = source_entity.merge(
        mapping,
        on=ENTITY_ID,
        how="left",
        validate="one_to_one",
    )
    missing = assignments.loc[assignments["stratum_id"].isna()].copy()

    return StrataPlanResult(
        entity_assignments=assignments,
        strata_plan=_build_strata_plan(assignments, variables),
        stratum_codebook=codebook,
        stratification_variables=variables,
        level_mapping=pd.DataFrame(),
        inconsistent_entity_values=mapping_issues,
        missing_entity_assignments=missing,
        names=names,
    )


def build_plan_from_existing_strata(
    df: pd.DataFrame,
    *,
    names: ReconciliationNames | None = None,
    stratum_column: str = "stratum_id",
) -> StrataPlanResult:
    """Build a strata plan from strata already attached to each entity.

    This is intended for child-level workflows such as EGE, where ``stratum_id``
    is inherited from the parent EJ rather than derived again at the child level.
    """
    names = names or ReconciliationNames.neutral()
    _require_columns(
        df,
        [names.entity_id_column, stratum_column],
        "table with existing strata",
    )

    inherited = df.loc[:, [names.entity_id_column, stratum_column]].copy()
    return load_entity_strata_mapping(
        df,
        inherited,
        names=names,
        mapping_entity_id_column=names.entity_id_column,
        mapping_stratum_column=stratum_column,
    )


def attach_stratification(
    source: pd.DataFrame,
    strata_result: StrataPlanResult,
    *,
    source_label: str = "source table",
) -> pd.DataFrame:
    """Attach authoritative entity-level strata and normalized stratum variables."""
    names = strata_result.names
    entity_column = names.entity_id_column

    if entity_column not in source.columns:
        raise KeyError(f"{source_label} is missing {entity_column!r}.")
    if "stratum_id" in source.columns:
        raise ValueError(
            f"{source_label} already contains 'stratum_id'; the source must be "
            "unstratified."
        )

    assignments = to_user_columns(strata_result.entity_assignments, names)
    variables = list(strata_result.stratification_variables)
    keep_columns = [entity_column, "stratum_id", *variables]
    _require_columns(assignments, keep_columns, "strata assignments")
    assignments = assignments.loc[:, keep_columns].copy()

    assignments["_entity_match_key"] = normalize_identifier_series(
        assignments[entity_column],
        pad_to_length=names.entity_pad_width,
    )
    if assignments["_entity_match_key"].duplicated().any():
        raise ValueError(
            f"{names.entity} strata assignments are not unique by {names.entity}."
        )

    lookup = assignments.set_index("_entity_match_key")
    source_keys = normalize_identifier_series(
        source[entity_column],
        pad_to_length=names.entity_pad_width,
    )
    missing_keys = sorted(set(source_keys.dropna()).difference(lookup.index))
    if missing_keys:
        raise ValueError(
            f"{source_label} contains {names.entity} values without a stratum: "
            f"{missing_keys[:20]}"
        )

    out = source.copy()
    for variable in variables:
        out[variable] = source_keys.map(lookup[variable])

    stratum_values = source_keys.map(lookup["stratum_id"]).astype("string")
    if variables:
        insert_after = variables[-1]
        insert_at = out.columns.get_loc(insert_after) + 1
    else:
        insert_at = out.columns.get_loc(entity_column) + 1
    out.insert(insert_at, "stratum_id", stratum_values)

    if out["stratum_id"].isna().any():
        raise ValueError(f"{source_label} contains missing stratum assignments.")
    return out


def _hash(value: Any, seed: str) -> str:
    return blake2b(f"{seed}|{value}".encode(), digest_size=16).hexdigest()


def build_reviewer_statistics(
    strata_plan: pd.DataFrame,
    *,
    reviewer_column: str = "reviewer",
) -> pd.DataFrame:
    """Count strata and entities assigned to each reviewer."""
    _require_columns(
        strata_plan,
        ["stratum_id", ENTITY_COUNT, reviewer_column],
        "strata plan",
    )
    work = strata_plan.copy()
    work[reviewer_column] = (
        work[reviewer_column].astype("string").fillna(UNASSIGNED_REVIEWER)
    )
    stats = (
        work.groupby(reviewer_column, dropna=False, sort=True)
        .agg(n_strata=("stratum_id", "nunique"), **{ENTITY_COUNT: (ENTITY_COUNT, "sum")})
        .reset_index()
        .rename(columns={reviewer_column: "reviewer"})
    )
    stats[["n_strata", ENTITY_COUNT]] = stats[
        ["n_strata", ENTITY_COUNT]
    ].astype("int64")
    return stats


def assign_reviewers_round_robin(
    strata_plan: pd.DataFrame,
    reviewers: Sequence[str],
    *,
    seed: str = "strata-reviewer-assignment",
    reviewer_column: str = "reviewer",
) -> ReviewerPlanResult:
    """Hash strata, sort them, then assign reviewers round-robin."""
    _require_columns(strata_plan, ["stratum_id", ENTITY_COUNT], "strata plan")
    reviewer_list = [str(value).strip() for value in reviewers if str(value).strip()]
    if not reviewer_list:
        raise ValueError("Provide at least one reviewer.")
    if len(set(reviewer_list)) != len(reviewer_list):
        raise ValueError("Reviewer names must be unique.")

    plan = strata_plan.copy()
    plan["_hash"] = plan["stratum_id"].map(lambda value: _hash(value, seed))
    plan = plan.sort_values(["_hash", "stratum_id"], kind="stable").reset_index(drop=True)
    plan[reviewer_column] = [
        reviewer_list[index % len(reviewer_list)] for index in range(len(plan))
    ]
    plan = (
        plan.drop(columns="_hash")
        .sort_values("stratum_id", kind="stable")
        .reset_index(drop=True)
    )
    return ReviewerPlanResult(
        strata_plan=plan,
        reviewer_statistics=build_reviewer_statistics(
            plan,
            reviewer_column=reviewer_column,
        ),
        missing_reviewer_assignments=pd.DataFrame(columns=plan.columns),
    )


def load_stratum_reviewer_mapping(
    strata_plan: pd.DataFrame,
    mapping_df: pd.DataFrame,
    *,
    mapping_stratum_column: str = "stratum_id",
    mapping_reviewer_column: str = "reviewer",
    reviewer_column: str = "reviewer",
) -> ReviewerPlanResult:
    """Attach an existing stratum-to-reviewer mapping."""
    _require_columns(strata_plan, ["stratum_id", ENTITY_COUNT], "strata plan")
    _require_columns(
        mapping_df,
        [mapping_stratum_column, mapping_reviewer_column],
        "stratum-to-reviewer mapping",
    )

    mapping = mapping_df.loc[
        :, [mapping_stratum_column, mapping_reviewer_column]
    ].copy()
    mapping = mapping.rename(
        columns={
            mapping_stratum_column: "stratum_id",
            mapping_reviewer_column: reviewer_column,
        }
    )
    mapping["stratum_id"] = (
        mapping["stratum_id"].astype("string").str.strip().replace("", pd.NA)
    )
    mapping[reviewer_column] = (
        mapping[reviewer_column].astype("string").str.strip().replace("", pd.NA)
    )
    if mapping["stratum_id"].isna().any():
        raise ValueError("The reviewer mapping contains a missing stratum_id.")

    conflicts = find_inconsistent_group_values(
        mapping,
        group_column="stratum_id",
        columns=[reviewer_column],
    )
    if not conflicts.empty:
        raise ValueError(
            "A stratum is assigned to more than one reviewer. Sample:\n"
            f"{conflicts.head(10).to_string(index=False)}"
        )

    mapping = mapping.drop_duplicates("stratum_id")
    plan_base = strata_plan.drop(columns=[reviewer_column], errors="ignore").copy()
    plan = plan_base.merge(
        mapping,
        on="stratum_id",
        how="left",
        validate="one_to_one",
    )
    missing = plan.loc[plan[reviewer_column].isna()].copy()

    return ReviewerPlanResult(
        strata_plan=plan,
        reviewer_statistics=build_reviewer_statistics(
            plan,
            reviewer_column=reviewer_column,
        ),
        missing_reviewer_assignments=missing,
    )


def merge_sample_sizes_into_review_plan(
    strata_plan: pd.DataFrame,
    sample_size_input: pd.DataFrame,
    *,
    population_column: str,
    maximum_sample_size_column: str | None = None,
    stratum_column: str = "stratum_id",
    reviewer_column: str = "reviewer",
    sample_size_column: str = "sample_size",
) -> SampleSizePlanResult:
    """Merge and validate manually entered stratum sample sizes.

    ``maximum_sample_size_column`` defaults to the total stratum population.
    EGE uses ``n_EGE_pooled`` instead so the second-stage sample cannot exceed
    the pooled EGE available in the sampled parent EJs.
    """
    maximum_column = maximum_sample_size_column or population_column

    required_plan = {
        stratum_column,
        population_column,
        reviewer_column,
        maximum_column,
    }
    required_sample = {stratum_column, sample_size_column}
    _require_columns(strata_plan, sorted(required_plan), "reviewer-assigned strata plan")
    _require_columns(sample_size_input, sorted(required_sample), "sample-size input")

    plan = strata_plan.copy()
    sample = sample_size_input.copy()

    for table, label in (
        (plan, "reviewer-assigned strata plan"),
        (sample, "sample-size input"),
    ):
        table[stratum_column] = (
            table[stratum_column].astype("string").str.strip().replace("", pd.NA)
        )
        if table[stratum_column].isna().any():
            raise ValueError(f"{label} contains missing {stratum_column} values.")
        duplicates = table.loc[
            table[stratum_column].duplicated(keep=False),
            stratum_column,
        ].drop_duplicates()
        if not duplicates.empty:
            raise ValueError(
                f"{label} contains duplicate stratum IDs: "
                f"{duplicates.head(10).tolist()}"
            )

    plan_ids = set(plan[stratum_column])
    sample_ids = set(sample[stratum_column])
    missing_ids = sorted(plan_ids - sample_ids)
    extra_ids = sorted(sample_ids - plan_ids)
    if missing_ids or extra_ids:
        details: list[str] = []
        if missing_ids:
            details.append(
                f"{len(missing_ids):,} stratum/strata missing from the sample-size "
                f"input; examples: {missing_ids[:10]}"
            )
        if extra_ids:
            details.append(
                f"{len(extra_ids):,} extra stratum/strata in the sample-size "
                f"input; examples: {extra_ids[:10]}"
            )
        raise ValueError(
            "The sample-size input must contain exactly the strata from the "
            "reviewer-assigned strata plan. " + " ".join(details)
        )

    plan[reviewer_column] = (
        plan[reviewer_column].astype("string").str.strip().replace("", pd.NA)
    )
    if plan[reviewer_column].isna().any():
        examples = plan.loc[
            plan[reviewer_column].isna(), stratum_column
        ].head(10).tolist()
        raise ValueError(
            "The reviewer-assigned strata plan contains strata without a reviewer. "
            f"Examples: {examples}"
        )

    numeric_columns = [population_column]
    if maximum_column != population_column:
        numeric_columns.append(maximum_column)

    for column in numeric_columns:
        numeric = pd.to_numeric(plan[column], errors="coerce")
        invalid = numeric.isna() | numeric.lt(0) | numeric.mod(1).ne(0)
        if invalid.any():
            examples = plan.loc[
                invalid, [stratum_column, column]
            ].head(10).to_dict("records")
            raise ValueError(
                f"{column} must contain non-negative integer counts. "
                f"Invalid values: {examples}"
            )
        plan[column] = numeric.astype("int64")

    if maximum_column != population_column:
        above_population = plan[maximum_column] > plan[population_column]
        if above_population.any():
            examples = plan.loc[
                above_population,
                [stratum_column, population_column, maximum_column],
            ].head(10).to_dict("records")
            raise ValueError(
                f"{maximum_column} cannot exceed {population_column}. "
                f"Invalid values: {examples}"
            )

    sample[sample_size_column] = (
        sample[sample_size_column].astype("string").str.strip().replace("", pd.NA)
    )
    sample_numeric = pd.to_numeric(sample[sample_size_column], errors="coerce")
    invalid_sample = (
        sample_numeric.isna()
        | sample_numeric.lt(0)
        | sample_numeric.mod(1).ne(0)
    )
    if invalid_sample.any():
        examples = sample.loc[
            invalid_sample, [stratum_column, sample_size_column]
        ].head(10).to_dict("records")
        raise ValueError(
            f"{sample_size_column} must contain one non-negative integer for every "
            f"stratum. Invalid values: {examples}"
        )
    sample[sample_size_column] = sample_numeric.astype("int64")

    lookup = sample.loc[:, [stratum_column, sample_size_column]].copy()
    plan = plan.drop(columns=[sample_size_column], errors="ignore")
    final_plan = plan.merge(
        lookup,
        on=stratum_column,
        how="left",
        validate="one_to_one",
    )
    if len(final_plan) != len(plan):
        raise RuntimeError(
            "The sample-size merge unexpectedly changed the number of strata."
        )

    above_maximum = final_plan[sample_size_column] > final_plan[maximum_column]
    if above_maximum.any():
        examples = final_plan.loc[
            above_maximum,
            [stratum_column, maximum_column, sample_size_column],
        ].head(10).to_dict("records")
        raise ValueError(
            f"{sample_size_column} cannot exceed {maximum_column}. "
            f"Invalid values: {examples}"
        )

    reviewer_statistics = (
        final_plan.groupby(
            reviewer_column,
            dropna=False,
            sort=True,
        )
        .agg(
            n_strata=(stratum_column, "nunique"),
            **{
                population_column: (population_column, "sum"),
                sample_size_column: (sample_size_column, "sum"),
            },
        )
        .reset_index()
    )
    reviewer_statistics["n_strata"] = reviewer_statistics["n_strata"].astype("int64")
    reviewer_statistics[population_column] = reviewer_statistics[
        population_column
    ].astype("int64")
    reviewer_statistics[sample_size_column] = reviewer_statistics[
        sample_size_column
    ].astype("int64")

    return SampleSizePlanResult(
        strata_plan=final_plan,
        sample_size_input=sample,
        reviewer_statistics=reviewer_statistics,
    )


def export_strata_outputs(
    entity_assignments: pd.DataFrame,
    strata_plan: pd.DataFrame,
    reviewer_statistics: pd.DataFrame,
    *,
    output_dir: str | Path,
    names: ReconciliationNames | None = None,
    workbook_filename: str = "strata_plan.xlsx",
    entity_assignments_filename: str = "entity_strata_assignments.parquet",
    reviewer_statistics_filename: str = "reviewer_statistics.xlsx",
    user_facing_columns: bool = False,
    overwrite: bool = True,
) -> dict[str, Path]:
    """Export canonical or user-facing assignments and plans.

    By default, exported tables keep the neutral columns ``entity_id`` and
    ``n_entity``. Set ``user_facing_columns=True`` and pass ``names`` to export
    columns such as ``EGE`` and ``n_EGE`` instead.
    """
    names = names or ReconciliationNames.neutral()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "workbook": output_dir / workbook_filename,
        "entity_assignments": output_dir / entity_assignments_filename,
        "reviewer_statistics": output_dir / reviewer_statistics_filename,
    }

    if not overwrite:
        existing = [path for path in paths.values() if path.exists()]
        if existing:
            raise FileExistsError(f"Outputs already exist: {existing}")

    tables = {
        "entity_assignments": entity_assignments.copy(),
        "strata_plan": strata_plan.copy(),
        "reviewer_statistics": reviewer_statistics.copy(),
    }
    if user_facing_columns:
        tables = {
            key: to_user_columns(table, names)
            for key, table in tables.items()
        }

    for table in tables.values():
        table.attrs = {}

    try:
        tables["entity_assignments"].to_parquet(
            paths["entity_assignments"],
            index=False,
        )
    except ImportError as exc:
        raise ImportError(
            "Parquet export requires pyarrow or fastparquet."
        ) from exc

    tables["strata_plan"].to_excel(
        paths["workbook"],
        sheet_name="strata_plan",
        index=False,
        engine="openpyxl",
    )
    tables["reviewer_statistics"].to_excel(
        paths["reviewer_statistics"],
        sheet_name="reviewer_statistics",
        index=False,
        engine="openpyxl",
    )
    return paths


__all__ = [
    "BUSINESS_ID",
    "DEFAULT_EGE_PAD_WIDTH",
    "DEFAULT_SIREN_PAD_WIDTH",
    "DEFAULT_SIRET_PAD_WIDTH",
    "ENTITY_COUNT",
    "ENTITY_ID",
    "MISSING_LEVEL",
    "UNASSIGNED_REVIEWER",
    "ReconciliationNames",
    "ReconciliationTableResult",
    "ReviewerPlanResult",
    "StrataPlanResult",
    "assign_reviewers_round_robin",
    "attach_stratification",
    "build_plan_from_existing_strata",
    "build_reviewer_statistics",
    "build_strata_from_variables",
    "export_strata_outputs",
    "find_inconsistent_entity_values",
    "find_inconsistent_group_values",
    "load_entity_strata_mapping",
    "load_stratum_reviewer_mapping",
    "load_table",
    "normalize_identifier_series",
    "prepare_reconciliation_table",
    "to_user_columns",
]
