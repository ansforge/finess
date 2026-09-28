"""Configurable FINESS/SIRENE reconciliation at entity or establishment level.

The same reconciliation engine supports both:

- EJ <-> SIREN reconciliation (legal-entity level)
- EGE <-> SIRET reconciliation (establishment level)

The core implementation uses the neutral internal names ``entity_id`` and
``business_id``. Public dataframes use the configured names (``EJ``/``siren``
or ``EGE``/``siret``), which keeps exported tables readable while avoiding two
copies of the business logic.

Typical use
-----------

EJ-SIREN remains the default for backward compatibility::

    finess = load_finess_database(...)
    sirene = load_sirene_database(...)
    corrected = load_ej_siren_dataset(...)
    table = build_consistency_table(finess, corrected1, corrected2)

For EGE-SIRET, pass the establishment configuration to the shared loaders and
processing functions::

    config = EGE_SIRET_CONFIG
    finess = load_finess_database(..., config=config)
    sirene = load_sirene_database(..., config=config)
    corrected = load_ege_siret_dataset(...)
    table = build_consistency_table(
        finess,
        corrected1,
        corrected2,
        config=config,
    )
"""

from __future__ import annotations

import warnings
from collections import defaultdict
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Public constants and configuration
# ---------------------------------------------------------------------------

FINESS_ID_PAD_WIDTH = 9
SIREN_KEY_PAD_WIDTH = 9
SIRET_KEY_PAD_WIDTH = 14

NO_INITIAL_BUSINESS_ID = "N/A"
NO_INITIAL_SIREN = NO_INITIAL_BUSINESS_ID  # Backward-compatible alias.
NO_INITIAL_SIRET = NO_INITIAL_BUSINESS_ID

EJ_KEY_PAD_WIDTH = FINESS_ID_PAD_WIDTH  # Backward-compatible alias.
EGE_KEY_PAD_WIDTH = FINESS_ID_PAD_WIDTH

_INTERNAL_ENTITY_COLUMN = "entity_id"
_INTERNAL_BUSINESS_ID_COLUMN = "business_id"
_CONFIG_ATTR = "reconciliation_config"
_DEFAULT = object()


@dataclass(frozen=True)
class ReconciliationConfig:
    """Names and normalization rules for one reconciliation level.

    Parameters
    ----------
    mode:
        Stable mode name, for example ``"EJ-SIREN"`` or ``"EGE-SIRET"``.
    entity_name:
        Human-readable FINESS identifier name.
    business_id_name:
        Human-readable SIRENE identifier name.
    entity_column:
        Standard entity column used in public/output dataframes.
    business_id_column:
        Standard business-identifier column used in public/output dataframes.
    entity_pad_width:
        Left-zero-padding width for FINESS identifiers.
    business_id_pad_width:
        Left-zero-padding width for SIRENE identifiers.
    """

    mode: str
    entity_name: str
    business_id_name: str
    entity_column: str
    business_id_column: str
    entity_pad_width: int | None
    business_id_pad_width: int | None

    def __post_init__(self) -> None:
        text_fields = {
            "mode": self.mode,
            "entity_name": self.entity_name,
            "business_id_name": self.business_id_name,
            "entity_column": self.entity_column,
            "business_id_column": self.business_id_column,
        }
        empty = [name for name, value in text_fields.items() if not str(value).strip()]
        if empty:
            raise ValueError(f"Configuration fields cannot be empty: {empty}")
        if self.entity_column == self.business_id_column:
            raise ValueError("Entity and business identifier columns must be different.")
        for field_name, width in (
            ("entity_pad_width", self.entity_pad_width),
            ("business_id_pad_width", self.business_id_pad_width),
        ):
            if width is not None and width <= 0:
                raise ValueError(f"{field_name} must be positive or None.")

    @property
    def initial_business_id_column(self) -> str:
        return f"initial_{self.business_id_column}"

    @property
    def business_id_proposal_column(self) -> str:
        return f"{self.business_id_column}_proposal"

    @property
    def is_initial_business_id_column(self) -> str:
        return f"is_initial_{self.business_id_column}"

    @property
    def entity_slug(self) -> str:
        return self.entity_name.strip().lower()


EJ_SIREN_CONFIG = ReconciliationConfig(
    mode="EJ-SIREN",
    entity_name="EJ",
    business_id_name="SIREN",
    entity_column="EJ",
    business_id_column="siren",
    entity_pad_width=FINESS_ID_PAD_WIDTH,
    business_id_pad_width=SIREN_KEY_PAD_WIDTH,
)

EGE_SIRET_CONFIG = ReconciliationConfig(
    mode="EGE-SIRET",
    entity_name="EGE",
    business_id_name="SIRET",
    entity_column="EGE",
    business_id_column="siret",
    entity_pad_width=FINESS_ID_PAD_WIDTH,
    business_id_pad_width=SIRET_KEY_PAD_WIDTH,
)


_CONFIG_ALIASES: dict[str, ReconciliationConfig] = {
    "EJ": EJ_SIREN_CONFIG,
    "EJ-SIREN": EJ_SIREN_CONFIG,
    "EJSIREN": EJ_SIREN_CONFIG,
    "LEGAL-ENTITY": EJ_SIREN_CONFIG,
    "LEGALENTITY": EJ_SIREN_CONFIG,
    "EGE": EGE_SIRET_CONFIG,
    "EGE-SIRET": EGE_SIRET_CONFIG,
    "EGESIRET": EGE_SIRET_CONFIG,
    "ESTABLISHMENT": EGE_SIRET_CONFIG,
}


def get_reconciliation_config(
    mode: str | ReconciliationConfig,
) -> ReconciliationConfig:
    """Return a validated configuration from a mode name or config object."""
    if isinstance(mode, ReconciliationConfig):
        return mode

    key = str(mode).strip().upper().replace("_", "-").replace(" ", "-")
    compact_key = key.replace("-", "")
    config = _CONFIG_ALIASES.get(key) or _CONFIG_ALIASES.get(compact_key)
    if config is None:
        supported = "EJ-SIREN, EGE-SIRET"
        raise ValueError(f"Unknown reconciliation mode {mode!r}. Supported modes: {supported}.")
    return config


def _config_from_attr(value: Any) -> ReconciliationConfig | None:
    if isinstance(value, ReconciliationConfig):
        return value
    if isinstance(value, Mapping):
        try:
            return ReconciliationConfig(**dict(value))
        except (TypeError, ValueError):
            return None
    if isinstance(value, str):
        try:
            return get_reconciliation_config(value)
        except ValueError:
            return None
    return None


def _resolve_config(
    config: str | ReconciliationConfig | None,
    *dataframes: pd.DataFrame | None,
) -> ReconciliationConfig:
    if config is not None:
        return get_reconciliation_config(config)

    discovered: list[ReconciliationConfig] = []
    for dataframe in dataframes:
        if dataframe is None:
            continue
        candidate = _config_from_attr(dataframe.attrs.get(_CONFIG_ATTR))
        if candidate is None:
            candidate = _config_from_attr(dataframe.attrs.get("reconciliation_mode"))
        if candidate is not None:
            discovered.append(candidate)

    if discovered:
        first = discovered[0]
        incompatible = [item.mode for item in discovered[1:] if item != first]
        if incompatible:
            raise ValueError(
                "Input dataframes carry incompatible reconciliation configurations: "
                f"{[first.mode, *incompatible]}"
            )
        return first

    return EJ_SIREN_CONFIG


def _attach_config(dataframe: pd.DataFrame, config: ReconciliationConfig) -> pd.DataFrame:
    dataframe.attrs[_CONFIG_ATTR] = config
    dataframe.attrs["reconciliation_mode"] = config.mode
    dataframe.attrs["reconciliation_config_dict"] = asdict(config)
    return dataframe


# ---------------------------------------------------------------------------
# File and identifier helpers
# ---------------------------------------------------------------------------


def _read_tabular_file(
    path: str | Path,
    sheet_name: int | str = 0,
    columns: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Read selected columns from a Parquet or Excel file."""
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".parquet":
        return pd.read_parquet(
            path,
            columns=list(columns) if columns is not None else None,
        )

    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(
            path,
            sheet_name=sheet_name,
            usecols=list(columns) if columns is not None else None,
        )

    raise ValueError(
        f"Unsupported file format for {path.name!r}: expected Parquet, XLSX, or XLS."
    )


def _normalize_identifier(value: Any, *, pad_to_length: int | None) -> Any:
    """Convert an identifier to text while preserving missing values."""
    if pd.isna(value):
        return pd.NA

    if isinstance(value, str):
        text = value.strip()
    elif isinstance(value, (np.integer, int)) and not isinstance(value, bool):
        text = str(int(value))
    elif isinstance(value, (np.floating, float)) and not isinstance(value, bool):
        if not np.isfinite(float(value)):
            return pd.NA
        if float(value).is_integer():
            text = str(int(value))
        else:
            text = format(float(value), "g")
    else:
        text = str(value).strip()

    if not text:
        return pd.NA

    if pad_to_length is not None and len(text) < pad_to_length:
        text = text.zfill(pad_to_length)

    return text


def _normalize_key_series(
    series: pd.Series,
    *,
    pad_to_length: int | None,
) -> pd.Series:
    return series.map(
        lambda value: _normalize_identifier(value, pad_to_length=pad_to_length)
    ).astype("string")


def _require_non_null(series: pd.Series, label: str) -> None:
    if series.isna().any():
        raise ValueError(f"Missing values found in required column {label!r}.")


def _ensure_unique(df: pd.DataFrame, subset: Sequence[str], label: str) -> None:
    duplicated = df.duplicated(subset=list(subset), keep=False)
    if duplicated.any():
        sample = df.loc[duplicated, list(subset)].head(10)
        raise ValueError(
            f"Duplicate {label} keys detected for columns {list(subset)!r}. "
            f"Sample:\n{sample.to_string(index=False)}"
        )


def _as_list_or_none(cols: Sequence[str] | None) -> list[str] | None:
    if cols is None:
        return None
    return list(cols)


def _require_columns(df: pd.DataFrame, columns: Sequence[str], label: str) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise KeyError(f"Missing columns in {label}: {missing}")


def validated_parent_enrichment(
    df: pd.DataFrame,
    *,
    parent_column: str,
    inherited_columns: Sequence[str],
    source: str = "parent enrichment table",
) -> pd.DataFrame:
    """Return one validated row per parent for child-level inheritance.

    Proposal tables contain several candidate rows per parent. A parent field may
    be inherited only when every row for that parent carries the same value,
    including the same missingness. This makes the former order-dependent
    ``drop_duplicates(..., keep='first')`` assumption explicit and blocking.
    """

    selected_columns = [parent_column, *inherited_columns]
    _require_columns(df, selected_columns, source)
    _require_non_null(df[parent_column], f"{source}.{parent_column}")

    conflicts: list[dict[str, Any]] = []
    grouped = df.loc[:, selected_columns].groupby(
        parent_column, sort=False, dropna=False
    )
    for column in inherited_columns:
        inconsistent = grouped[column].nunique(dropna=False).gt(1)
        for parent in inconsistent.index[inconsistent][:10]:
            values = grouped.get_group(parent)[column].drop_duplicates().tolist()
            conflicts.append(
                {
                    parent_column: parent,
                    "column": column,
                    "values": values,
                }
            )

    if conflicts:
        sample = pd.DataFrame(conflicts).head(20)
        raise ValueError(
            f"{source} has conflicting fields within {parent_column} groups. "
            "Resolve the parent data before EGE inheritance. Sample:\n"
            f"{sample.to_string(index=False)}"
        )

    result = df.loc[:, selected_columns].drop_duplicates(
        subset=parent_column, keep="first"
    )
    _ensure_unique(result, [parent_column], f"{source} parent")
    return result.reset_index(drop=True)


def _select_existing_column(
    df: pd.DataFrame,
    *,
    explicit: str | None,
    candidates: Sequence[str],
    label: str,
) -> str:
    if explicit is not None:
        if explicit not in df.columns:
            raise KeyError(f"Column {explicit!r} not found in {label} dataframe.")
        return explicit

    for candidate in candidates:
        if candidate in df.columns:
            return candidate

    raise KeyError(
        f"Could not identify the {label} column. Tried: {list(dict.fromkeys(candidates))}"
    )


def _coalesce_alias(
    generic_value: str | None,
    legacy_value: str | None,
    *,
    generic_name: str,
    legacy_name: str,
) -> str | None:
    if (
        generic_value is not None
        and legacy_value is not None
        and generic_value != legacy_value
    ):
        raise ValueError(
            f"Conflicting values supplied for {generic_name!r} and legacy alias "
            f"{legacy_name!r}."
        )
    return generic_value if generic_value is not None else legacy_value


def _coalesce_width_alias(
    generic_value: int | None,
    legacy_value: int | None,
    *,
    default: int | None,
    generic_name: str,
    legacy_name: str,
) -> int | None:
    if (
        generic_value is not None
        and legacy_value is not None
        and generic_value != legacy_value
    ):
        raise ValueError(
            f"Conflicting values supplied for {generic_name!r} and legacy alias "
            f"{legacy_name!r}."
        )
    if generic_value is not None:
        return generic_value
    if legacy_value is not None:
        return legacy_value
    return default


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _load_database(
    path: str | Path,
    key_column: str,
    keep_columns: Sequence[str] | None = None,
    *,
    sheet_name: int | str = 0,
    rename_key_to: str | None = None,
    pad_to_length: int | None,
    config: ReconciliationConfig,
) -> pd.DataFrame:
    """Shared implementation for loading FINESS and SIRENE databases."""
    
    selected_cols = [
        key_column,
        *[
            column
            for column in (_as_list_or_none(keep_columns) or [])
            if column != key_column
        ],
    ]

    df = _read_tabular_file(
        path,
        sheet_name=sheet_name,
        columns=selected_cols,
    ).copy()

    _require_columns(df, selected_cols, str(path))

    df = df.loc[:, selected_cols].copy()
    df[key_column] = _normalize_key_series(
        df[key_column],
        pad_to_length=pad_to_length,
    )

    _require_non_null(df[key_column], key_column)
    _ensure_unique(df, [key_column], label="organization")

    if rename_key_to is not None and rename_key_to != key_column:
        if rename_key_to in df.columns:
            raise ValueError(
                f"Cannot rename {key_column!r} to {rename_key_to!r}: the target column "
                "already exists in the selected data."
            )
        df = df.rename(columns={key_column: rename_key_to})

    return _attach_config(df, config)


def load_finess_database(
    path: str | Path,
    key_column: str,
    keep_columns: Sequence[str] | None = None,
    *,
    sheet_name: int | str = 0,
    rename_key_to: str | None | object = _DEFAULT,
    pad_to_length: int | None | object = _DEFAULT,
    config: str | ReconciliationConfig = EJ_SIREN_CONFIG,
) -> pd.DataFrame:
    """Read a FINESS entity database.

    With ``EJ_SIREN_CONFIG`` the key is renamed to ``EJ``. With
    ``EGE_SIRET_CONFIG`` it is renamed to ``EGE``. Pass ``rename_key_to=None``
    to retain the source column name.
    """
    resolved = get_reconciliation_config(config)
    target = resolved.entity_column if rename_key_to is _DEFAULT else rename_key_to
    width = resolved.entity_pad_width if pad_to_length is _DEFAULT else pad_to_length

    return _load_database(
        path=path,
        key_column=key_column,
        keep_columns=keep_columns,
        sheet_name=sheet_name,
        rename_key_to=target,  # type: ignore[arg-type]
        pad_to_length=width,  # type: ignore[arg-type]
        config=resolved,
    )


def load_sirene_database(
    path: str | Path,
    key_column: str,
    keep_columns: Sequence[str] | None = None,
    *,
    sheet_name: int | str = 0,
    rename_key_to: str | None | object = _DEFAULT,
    pad_to_length: int | None | object = _DEFAULT,
    config: str | ReconciliationConfig = EJ_SIREN_CONFIG,
) -> pd.DataFrame:
    """Read a SIRENE identifier database.

    The default output key is ``siren`` for EJ-SIREN and ``siret`` for
    EGE-SIRET.
    """
    resolved = get_reconciliation_config(config)
    target = (
        resolved.business_id_column if rename_key_to is _DEFAULT else rename_key_to
    )
    width = (
        resolved.business_id_pad_width
        if pad_to_length is _DEFAULT
        else pad_to_length
    )

    return _load_database(
        path=path,
        key_column=key_column,
        keep_columns=keep_columns,
        sheet_name=sheet_name,
        rename_key_to=target,  # type: ignore[arg-type]
        pad_to_length=width,  # type: ignore[arg-type]
        config=resolved,
    )


def load_sirene_database_for_identifiers(
    path: str | Path,
    key_column: str,
    identifiers: Collection[Any],
    keep_columns: Sequence[str] | None = None,
    *,
    sheet_name: int | str = 0,
    rename_key_to: str | None | object = _DEFAULT,
    pad_to_length: int | None | object = _DEFAULT,
    config: str | ReconciliationConfig = EJ_SIREN_CONFIG,
) -> pd.DataFrame:
    """Read only SIRENE rows referenced by the supplied identifiers.

    Parquet inputs use predicate pushdown on the physical SIRENE key, avoiding a
    full scan materialization in pandas. The returned dataframe follows the same
    normalization, uniqueness and public-column rules as :func:`load_sirene_database`.

    Only duplicate keys among the requested identifiers are relevant and therefore
    validated. Rows for unrelated SIRENE identifiers are intentionally not loaded.
    """
    resolved = get_reconciliation_config(config)
    target = (
        resolved.business_id_column if rename_key_to is _DEFAULT else rename_key_to
    )
    width = (
        resolved.business_id_pad_width
        if pad_to_length is _DEFAULT
        else pad_to_length
    )

    requested = sorted(
        {
            str(normalized)
            for value in identifiers
            if (
                normalized := _normalize_identifier(
                    value,
                    pad_to_length=width,  # type: ignore[arg-type]
                )
            )
            is not pd.NA
        }
    )

    selected_cols = [
        key_column,
        *[
            column
            for column in (_as_list_or_none(keep_columns) or [])
            if column != key_column
        ],
    ]

    path = Path(path)
    if not requested:
        empty = pd.DataFrame(columns=selected_cols)
        if target is not None and target != key_column:
            empty = empty.rename(columns={key_column: target})
        return _attach_config(empty, resolved)

    if path.suffix.lower() == ".parquet":
        df = pd.read_parquet(
            path,
            columns=selected_cols,
            filters=[(key_column, "in", requested)],
        ).copy()
    else:
        df = _read_tabular_file(
            path,
            sheet_name=sheet_name,
            columns=selected_cols,
        ).copy()

    _require_columns(df, selected_cols, str(path))
    df[key_column] = _normalize_key_series(
        df[key_column],
        pad_to_length=width,  # type: ignore[arg-type]
    )

    requested_set = set(requested)
    df = df.loc[df[key_column].isin(requested_set), selected_cols].copy()
    _require_non_null(df[key_column], key_column)
    _ensure_unique(df, [key_column], label="requested SIRENE identifier")

    if target is not None and target != key_column:
        if target in df.columns:
            raise ValueError(
                f"Cannot rename {key_column!r} to {target!r}: the target column "
                "already exists in the selected data."
            )
        df = df.rename(columns={key_column: target})

    return _attach_config(df, resolved)


def load_reconciliation_dataset(
    path: str | Path,
    entity_column: str,
    business_id_column: str,
    dataset_name: str,
    keep_columns: Sequence[str] | None = None,
    *,
    sheet_name: int | str = 0,
    config: str | ReconciliationConfig = EJ_SIREN_CONFIG,
    entity_pad_to_length: int | None | object = _DEFAULT,
    business_id_pad_to_length: int | None | object = _DEFAULT,
) -> pd.DataFrame:
    """Read one corrected reconciliation dataset.

    Source columns are renamed to the configured standard public columns. For
    example, EJ-SIREN returns ``EJ`` and ``siren`` while EGE-SIRET returns
    ``EGE`` and ``siret``.
    """
    resolved = get_reconciliation_config(config)
    entity_width = (
        resolved.entity_pad_width
        if entity_pad_to_length is _DEFAULT
        else entity_pad_to_length
    )
    business_width = (
        resolved.business_id_pad_width
        if business_id_pad_to_length is _DEFAULT
        else business_id_pad_to_length
    )

    df = _read_tabular_file(path, sheet_name=sheet_name).copy()
    required = [entity_column, business_id_column]
    _require_columns(df, required, str(path))

    selected_cols = required + [
        column
        for column in (_as_list_or_none(keep_columns) or [])
        if column not in required
    ]
    _require_columns(df, selected_cols, str(path))

    reserved_targets = {
        resolved.entity_column: entity_column,
        resolved.business_id_column: business_id_column,
    }
    for target, source in reserved_targets.items():
        if target in selected_cols and target != source:
            raise ValueError(
                f"Selected column {target!r} conflicts with the configured output "
                f"name for source column {source!r}."
            )

    df = df.loc[:, selected_cols].copy()
    df[entity_column] = _normalize_key_series(
        df[entity_column],
        pad_to_length=entity_width,  # type: ignore[arg-type]
    )
    df[business_id_column] = _normalize_key_series(
        df[business_id_column],
        pad_to_length=business_width,  # type: ignore[arg-type]
    )

    _require_non_null(df[entity_column], entity_column)
    _require_non_null(df[business_id_column], business_id_column)
    _ensure_unique(
        df,
        [entity_column, business_id_column],
        label=(
            f"dataset {dataset_name!r} "
            f"({resolved.entity_name}, {resolved.business_id_name}) pairs"
        ),
    )

    df = df.rename(
        columns={
            entity_column: resolved.entity_column,
            business_id_column: resolved.business_id_column,
        }
    )
    df.attrs["dataset_name"] = dataset_name
    return _attach_config(df, resolved)


def load_ej_siren_dataset(
    path: str | Path,
    ej_column: str,
    siren_column: str,
    dataset_name: str,
    keep_columns: Sequence[str] | None = None,
    *,
    sheet_name: int | str = 0,
    ej_pad_to_length: int | None = EJ_KEY_PAD_WIDTH,
    siren_pad_to_length: int | None = SIREN_KEY_PAD_WIDTH,
) -> pd.DataFrame:
    """Backward-compatible loader for a corrected EJ-SIREN dataset."""
    return load_reconciliation_dataset(
        path=path,
        entity_column=ej_column,
        business_id_column=siren_column,
        dataset_name=dataset_name,
        keep_columns=keep_columns,
        sheet_name=sheet_name,
        config=EJ_SIREN_CONFIG,
        entity_pad_to_length=ej_pad_to_length,
        business_id_pad_to_length=siren_pad_to_length,
    )


def load_ege_siret_dataset(
    path: str | Path,
    ege_column: str,
    siret_column: str,
    dataset_name: str,
    keep_columns: Sequence[str] | None = None,
    *,
    sheet_name: int | str = 0,
    ege_pad_to_length: int | None = EGE_KEY_PAD_WIDTH,
    siret_pad_to_length: int | None = SIRET_KEY_PAD_WIDTH,
) -> pd.DataFrame:
    """Load a corrected EGE-SIRET dataset."""
    return load_reconciliation_dataset(
        path=path,
        entity_column=ege_column,
        business_id_column=siret_column,
        dataset_name=dataset_name,
        keep_columns=keep_columns,
        sheet_name=sheet_name,
        config=EGE_SIRET_CONFIG,
        entity_pad_to_length=ege_pad_to_length,
        business_id_pad_to_length=siret_pad_to_length,
    )


# ---------------------------------------------------------------------------
# Consistency table
# ---------------------------------------------------------------------------


def _unique_sorted(values: Sequence[Any]) -> tuple[str, ...]:
    unique = pd.Index(list(values)).drop_duplicates()
    return tuple(sorted((str(value) for value in unique.tolist()), key=str))


def _to_internal_pair_frame(
    df: pd.DataFrame,
    *,
    config: ReconciliationConfig,
    entity_column: str | None = None,
    business_id_column: str | None = None,
    label: str,
) -> pd.DataFrame:
    selected_entity = _select_existing_column(
        df,
        explicit=entity_column,
        candidates=(config.entity_column, _INTERNAL_ENTITY_COLUMN),
        label=f"{label} entity",
    )
    selected_business = _select_existing_column(
        df,
        explicit=business_id_column,
        candidates=(config.business_id_column, _INTERNAL_BUSINESS_ID_COLUMN),
        label=f"{label} business identifier",
    )

    out = df.loc[:, [selected_entity, selected_business]].rename(
        columns={
            selected_entity: _INTERNAL_ENTITY_COLUMN,
            selected_business: _INTERNAL_BUSINESS_ID_COLUMN,
        }
    )
    out[_INTERNAL_ENTITY_COLUMN] = _normalize_key_series(
        out[_INTERNAL_ENTITY_COLUMN],
        pad_to_length=config.entity_pad_width,
    )
    out[_INTERNAL_BUSINESS_ID_COLUMN] = _normalize_key_series(
        out[_INTERNAL_BUSINESS_ID_COLUMN],
        pad_to_length=config.business_id_pad_width,
    )
    _require_non_null(out[_INTERNAL_ENTITY_COLUMN], selected_entity)
    _require_non_null(out[_INTERNAL_BUSINESS_ID_COLUMN], selected_business)
    return out


def _proposals_by_entity(
    df: pd.DataFrame,
    *,
    config: ReconciliationConfig,
    label: str,
) -> pd.DataFrame:
    internal = _to_internal_pair_frame(df, config=config, label=label)
    if internal.empty:
        return pd.DataFrame(
            columns=[_INTERNAL_ENTITY_COLUMN, "proposals", "proposal_count"]
        )

    out = (
        internal.groupby(_INTERNAL_ENTITY_COLUMN, sort=False)[
            _INTERNAL_BUSINESS_ID_COLUMN
        ]
        .agg(lambda series: _unique_sorted(series.tolist()))
        .rename("proposals")
        .to_frame()
        .reset_index()
    )
    out["proposal_count"] = out["proposals"].map(len).astype("int64")
    return out


def _normalize_tuple_cell(value: Any) -> tuple[str, ...]:
    if value is None or value is pd.NA:
        return ()
    if isinstance(value, float) and np.isnan(value):
        return ()
    if isinstance(value, (list, tuple, set, pd.Index, np.ndarray)):
        return tuple(str(item) for item in value)
    return ()


def _consistency_type(row: pd.Series) -> str:
    proposals1 = set(row["dataset1__proposals"])
    proposals2 = set(row["dataset2__proposals"])
    if proposals1 and proposals2 and proposals1 == proposals2:
        return "Total consistency"
    if proposals1.intersection(proposals2):
        return "Partial consistency"
    return "Total inconsistency"


def _entity_set(df: pd.DataFrame, column: str) -> set[str]:
    return set(df[column].dropna().astype("string").tolist())


def _normalize_entity_collection(
    values: Collection[Any] | None,
    *,
    config: ReconciliationConfig,
) -> set[str]:
    """Normalize optional entity identifiers to the configured identifier width."""
    if not values:
        return set()

    normalized: set[str] = set()
    for value in values:
        item = _normalize_identifier(
            value,
            pad_to_length=config.entity_pad_width,
        )
        if pd.notna(item):
            normalized.add(str(item))
    return normalized


def _warn_orphan_entities(
    dataset_name: str,
    orphan_entities: Collection[str],
    *,
    config: ReconciliationConfig,
    max_examples: int = 10,
) -> None:
    orphan_ids = sorted(str(value) for value in orphan_entities)
    orphan_count = len(orphan_ids)
    if orphan_count == 0:
        return

    example_ids = orphan_ids[:max_examples]
    example_suffix = (
        f" Examples: {', '.join(example_ids)} "
        f"({len(example_ids)} of {orphan_count} shown)."
    )

    warnings.warn(
        f"{orphan_count} {config.entity_name}(s) found in {dataset_name} are "
        "unexpectedly absent from the FINESS analysis scope; they will be "
        "excluded from the consistency table (left join on FINESS)."
        + example_suffix,
        UserWarning,
        stacklevel=2,
    )


def build_consistency_table(
    finess_df: pd.DataFrame,
    dataset1_df: pd.DataFrame,
    dataset2_df: pd.DataFrame,
    *,
    config: str | ReconciliationConfig | None = None,
    finess_entity_column: str | None = None,
    finess_ej_column: str | None = None,
    known_out_of_scope_entities: Collection[Any] | None = None,
) -> pd.DataFrame:
    """Build the consistency table from all configured FINESS entities.

    ``finess_ej_column`` is retained as a backward-compatible alias for
    ``finess_entity_column``.

    ``known_out_of_scope_entities`` may list entities intentionally removed before
    reconciliation. They remain absent from the consistency table but are separated
    from unexpected source orphans for diagnostics.
    """
    resolved = _resolve_config(config, finess_df, dataset1_df, dataset2_df)
    selected_finess_column = _coalesce_alias(
        finess_entity_column,
        finess_ej_column,
        generic_name="finess_entity_column",
        legacy_name="finess_ej_column",
    )
    selected_finess_column = _select_existing_column(
        finess_df,
        explicit=selected_finess_column,
        candidates=(resolved.entity_column, _INTERNAL_ENTITY_COLUMN),
        label="FINESS entity",
    )

    base = (
        finess_df.loc[:, [selected_finess_column]]
        .rename(columns={selected_finess_column: _INTERNAL_ENTITY_COLUMN})
        .copy()
    )
    base[_INTERNAL_ENTITY_COLUMN] = _normalize_key_series(
        base[_INTERNAL_ENTITY_COLUMN],
        pad_to_length=resolved.entity_pad_width,
    )
    _require_non_null(base[_INTERNAL_ENTITY_COLUMN], selected_finess_column)
    _ensure_unique(base, [_INTERNAL_ENTITY_COLUMN], label="FINESS entity")

    dataset1_internal = _to_internal_pair_frame(
        dataset1_df,
        config=resolved,
        label="dataset1",
    )
    dataset2_internal = _to_internal_pair_frame(
        dataset2_df,
        config=resolved,
        label="dataset2",
    )

    finess_entities = _entity_set(base, _INTERNAL_ENTITY_COLUMN)
    dataset1_entities = _entity_set(dataset1_internal, _INTERNAL_ENTITY_COLUMN)
    dataset2_entities = _entity_set(dataset2_internal, _INTERNAL_ENTITY_COLUMN)

    dataset1_orphans = dataset1_entities - finess_entities
    dataset2_orphans = dataset2_entities - finess_entities

    known_out_of_scope = _normalize_entity_collection(
        known_out_of_scope_entities,
        config=resolved,
    )
    dataset1_out_of_scope = dataset1_orphans & known_out_of_scope
    dataset2_out_of_scope = dataset2_orphans & known_out_of_scope
    dataset1_unexpected_orphans = dataset1_orphans - known_out_of_scope
    dataset2_unexpected_orphans = dataset2_orphans - known_out_of_scope

    dataset1_name = dataset1_df.attrs.get("dataset_name", "dataset1")
    dataset2_name = dataset2_df.attrs.get("dataset_name", "dataset2")
    _warn_orphan_entities(
        dataset1_name,
        dataset1_unexpected_orphans,
        config=resolved,
    )
    _warn_orphan_entities(
        dataset2_name,
        dataset2_unexpected_orphans,
        config=resolved,
    )

    dataset1_grouped = _proposals_by_entity(
        dataset1_df,
        config=resolved,
        label="dataset1",
    ).rename(
        columns={
            "proposals": "dataset1__proposals",
            "proposal_count": "dataset1__proposal_count",
        }
    )
    dataset2_grouped = _proposals_by_entity(
        dataset2_df,
        config=resolved,
        label="dataset2",
    ).rename(
        columns={
            "proposals": "dataset2__proposals",
            "proposal_count": "dataset2__proposal_count",
        }
    )

    table = base.merge(
        dataset1_grouped,
        on=_INTERNAL_ENTITY_COLUMN,
        how="left",
    ).merge(
        dataset2_grouped,
        on=_INTERNAL_ENTITY_COLUMN,
        how="left",
    )

    table["dataset1__proposals"] = table["dataset1__proposals"].apply(
        _normalize_tuple_cell
    )
    table["dataset2__proposals"] = table["dataset2__proposals"].apply(
        _normalize_tuple_cell
    )
    table["dataset1__proposal_count"] = (
        table["dataset1__proposal_count"].fillna(0).astype("int64")
    )
    table["dataset2__proposal_count"] = (
        table["dataset2__proposal_count"].fillna(0).astype("int64")
    )
    table["consistency_type"] = table.apply(_consistency_type, axis=1)

    both_total = dataset1_entities & dataset2_entities
    both_in_finess = both_total & finess_entities

    table = table.rename(
        columns={_INTERNAL_ENTITY_COLUMN: resolved.entity_column}
    )
    table.attrs["dataset1_name"] = dataset1_name
    table.attrs["dataset2_name"] = dataset2_name

    # Generic metadata.
    table.attrs["finess_entity_count"] = len(finess_entities)
    table.attrs["dataset1_entity_total_count"] = len(dataset1_entities)
    table.attrs["dataset2_entity_total_count"] = len(dataset2_entities)
    table.attrs["dataset1_entity_in_finess_count"] = len(
        dataset1_entities & finess_entities
    )
    table.attrs["dataset2_entity_in_finess_count"] = len(
        dataset2_entities & finess_entities
    )
    table.attrs["dataset1_orphan_entity_count"] = len(dataset1_orphans)
    table.attrs["dataset2_orphan_entity_count"] = len(dataset2_orphans)
    table.attrs["dataset1_out_of_scope_entity_count"] = len(dataset1_out_of_scope)
    table.attrs["dataset2_out_of_scope_entity_count"] = len(dataset2_out_of_scope)
    table.attrs["dataset1_unexpected_orphan_entity_count"] = len(
        dataset1_unexpected_orphans
    )
    table.attrs["dataset2_unexpected_orphan_entity_count"] = len(
        dataset2_unexpected_orphans
    )
    table.attrs["entity_in_both_datasets_total_count"] = len(both_total)
    table.attrs["entity_in_both_datasets_in_finess_count"] = len(both_in_finess)

    # Existing EJ metadata names remain available in EJ mode.
    if resolved == EJ_SIREN_CONFIG:
        table.attrs["finess_ej_count"] = len(finess_entities)
        table.attrs["dataset1_ej_total_count"] = len(dataset1_entities)
        table.attrs["dataset2_ej_total_count"] = len(dataset2_entities)
        table.attrs["dataset1_ej_in_finess_count"] = len(
            dataset1_entities & finess_entities
        )
        table.attrs["dataset2_ej_in_finess_count"] = len(
            dataset2_entities & finess_entities
        )
        table.attrs["dataset1_orphan_ej_count"] = len(dataset1_orphans)
        table.attrs["dataset2_orphan_ej_count"] = len(dataset2_orphans)
        table.attrs["dataset1_out_of_scope_ej_count"] = len(dataset1_out_of_scope)
        table.attrs["dataset2_out_of_scope_ej_count"] = len(dataset2_out_of_scope)
        table.attrs["dataset1_unexpected_orphan_ej_count"] = len(
            dataset1_unexpected_orphans
        )
        table.attrs["dataset2_unexpected_orphan_ej_count"] = len(
            dataset2_unexpected_orphans
        )
        table.attrs["ej_in_both_datasets_total_count"] = len(both_total)

    return _attach_config(table, resolved)


# ---------------------------------------------------------------------------
# Statistics and enrichment
# ---------------------------------------------------------------------------


def compute_main_statistics(
    consistency_table: pd.DataFrame,
    *,
    config: str | ReconciliationConfig | None = None,
) -> dict[str, dict[str, float | int]]:
    """Compute generic statistics plus level-specific compatibility aliases."""
    resolved = _resolve_config(config, consistency_table)
    entity_column = _select_existing_column(
        consistency_table,
        explicit=None,
        candidates=(resolved.entity_column, _INTERNAL_ENTITY_COLUMN),
        label="consistency-table entity",
    )

    required = {
        entity_column,
        "dataset1__proposal_count",
        "dataset2__proposal_count",
        "consistency_type",
    }
    missing = required - set(consistency_table.columns)
    if missing:
        raise KeyError(f"Consistency table is missing columns: {sorted(missing)}")

    total_entities = int(consistency_table[entity_column].nunique(dropna=True))
    finess_count = int(
        consistency_table.attrs.get("finess_entity_count", total_entities)
    )
    dataset1_count = int(
        consistency_table.attrs.get(
            "dataset1_entity_total_count",
            (consistency_table["dataset1__proposal_count"] > 0).sum(),
        )
    )
    dataset2_count = int(
        consistency_table.attrs.get(
            "dataset2_entity_total_count",
            (consistency_table["dataset2__proposal_count"] > 0).sum(),
        )
    )

    both_mask = (
        (consistency_table["dataset1__proposal_count"] > 0)
        & (consistency_table["dataset2__proposal_count"] > 0)
    )
    both_in_finess_count = int(
        consistency_table.attrs.get(
            "entity_in_both_datasets_in_finess_count",
            both_mask.sum(),
        )
    )
    both_total_count = int(
        consistency_table.attrs.get(
            "entity_in_both_datasets_total_count",
            both_in_finess_count,
        )
    )

    def _summary(df: pd.DataFrame) -> dict[str, float | int]:
        if df.empty:
            return {
                "total_consistency_n": 0,
                "total_consistency_rate": 0.0,
                "partial_consistency_n": 0,
                "partial_consistency_rate": 0.0,
                "total_inconsistency_n": 0,
                "total_inconsistency_rate": 0.0,
                "avg_dataset1_proposals": 0.0,
                "avg_dataset2_proposals": 0.0,
            }

        return {
            "total_consistency_n": int(
                (df["consistency_type"] == "Total consistency").sum()
            ),
            "total_consistency_rate": float(
                (df["consistency_type"] == "Total consistency").mean()
            ),
            "partial_consistency_n": int(
                (df["consistency_type"] == "Partial consistency").sum()
            ),
            "partial_consistency_rate": float(
                (df["consistency_type"] == "Partial consistency").mean()
            ),
            "total_inconsistency_n": int(
                (df["consistency_type"] == "Total inconsistency").sum()
            ),
            "total_inconsistency_rate": float(
                (df["consistency_type"] == "Total inconsistency").mean()
            ),
            "avg_dataset1_proposals": float(
                df["dataset1__proposal_count"].mean()
            ),
            "avg_dataset2_proposals": float(
                df["dataset2__proposal_count"].mean()
            ),
        }

    all_stats = _summary(consistency_table)
    both_stats = _summary(consistency_table.loc[both_mask].copy())

    general: dict[str, float | int] = {
        "n_entities_finess": finess_count,
        "n_entities_dataset1": dataset1_count,
        "n_entities_dataset2": dataset2_count,
        "n_entities_in_both_datasets": both_total_count,
        "n_entities_in_both_datasets_and_finess": both_in_finess_count,
        "pct_entities_in_both_datasets_over_finess": (
            float(both_in_finess_count / finess_count) if finess_count else 0.0
        ),
    }

    # Readable aliases specific to the configured entity type.
    slug = resolved.entity_slug
    general.update(
        {
            f"n_{slug}_finess": finess_count,
            f"n_{slug}_dataset1": dataset1_count,
            f"n_{slug}_dataset2": dataset2_count,
            f"n_{slug}_in_both_datasets": both_total_count,
            f"n_{slug}_in_both_datasets_and_finess": both_in_finess_count,
            f"pct_{slug}_in_both_datasets_over_finess": (
                float(both_in_finess_count / finess_count)
                if finess_count
                else 0.0
            ),
        }
    )

    result: dict[str, dict[str, float | int]] = {
        "general": general,
        "all_finess_entities": all_stats,
        "entities_in_both_datasets": both_stats,
    }

    # Preserve the original EJ section names and offer symmetric EGE names.
    result[f"all_finess_{slug}s"] = all_stats.copy()
    result[f"{slug}s_in_both_datasets"] = both_stats.copy()
    return result


def enrich_consistency_table(
    consistency_table: pd.DataFrame,
    *,
    finess_df: pd.DataFrame | None = None,
    dataset1_df: pd.DataFrame | None = None,
    dataset2_df: pd.DataFrame | None = None,
    finess_columns: Sequence[str] | None = None,
    dataset1_columns: Sequence[str] | None = None,
    dataset2_columns: Sequence[str] | None = None,
    config: str | ReconciliationConfig | None = None,
) -> pd.DataFrame:
    """Optionally enrich a consistency table with source-table columns."""
    resolved = _resolve_config(
        config,
        consistency_table,
        finess_df,
        dataset1_df,
        dataset2_df,
    )
    output_entity_column = _select_existing_column(
        consistency_table,
        explicit=None,
        candidates=(resolved.entity_column, _INTERNAL_ENTITY_COLUMN),
        label="consistency-table entity",
    )

    enriched = consistency_table.copy()
    original_attrs = dict(consistency_table.attrs)

    if finess_df is not None and finess_columns:
        finess_entity_column = _select_existing_column(
            finess_df,
            explicit=None,
            candidates=(resolved.entity_column, _INTERNAL_ENTITY_COLUMN),
            label="FINESS entity",
        )
        needed = [finess_entity_column] + [
            column for column in finess_columns if column != finess_entity_column
        ]
        _require_columns(finess_df, needed, "FINESS dataframe")
        tmp = finess_df.loc[:, needed].copy()
        _ensure_unique(tmp, [finess_entity_column], label="FINESS entity")
        tmp = tmp.rename(
            columns={
                finess_entity_column: output_entity_column,
                **{
                    column: f"finess__{column}"
                    for column in finess_columns
                    if column != finess_entity_column
                },
            }
        )
        enriched = enriched.merge(tmp, on=output_entity_column, how="left")

    if dataset1_df is not None and dataset1_columns:
        enriched = _merge_dataset_columns(
            enriched,
            dataset1_df,
            dataset1_columns,
            prefix="dataset1",
            config=resolved,
            output_entity_column=output_entity_column,
        )
    if dataset2_df is not None and dataset2_columns:
        enriched = _merge_dataset_columns(
            enriched,
            dataset2_df,
            dataset2_columns,
            prefix="dataset2",
            config=resolved,
            output_entity_column=output_entity_column,
        )

    enriched.attrs.update(original_attrs)
    return _attach_config(enriched, resolved)


def _merge_dataset_columns(
    enriched: pd.DataFrame,
    dataset_df: pd.DataFrame,
    columns: Sequence[str],
    *,
    prefix: str,
    config: ReconciliationConfig,
    output_entity_column: str,
) -> pd.DataFrame:
    dataset_entity_column = _select_existing_column(
        dataset_df,
        explicit=None,
        candidates=(config.entity_column, _INTERNAL_ENTITY_COLUMN),
        label=f"{prefix} entity",
    )
    needed = [dataset_entity_column] + [
        column for column in columns if column != dataset_entity_column
    ]
    _require_columns(dataset_df, needed, prefix)

    per_entity_counts = dataset_df.groupby(dataset_entity_column, sort=False).size()
    if (per_entity_counts > 1).any():
        raise ValueError(
            f"{prefix} contains more than one row for at least one "
            f"{config.entity_name}; cannot safely enrich selected columns."
        )

    tmp = dataset_df.loc[:, needed].rename(
        columns={
            dataset_entity_column: output_entity_column,
            **{
                column: f"{prefix}__{column}"
                for column in columns
                if column != dataset_entity_column
            },
        }
    )
    return enriched.merge(tmp, on=output_entity_column, how="left")


def apply_derived_columns(
    enriched_table: pd.DataFrame,
    derived_columns: Mapping[str, Callable[[pd.DataFrame], Any]],
) -> pd.DataFrame:
    """Add columns computed from the full dataframe."""
    out = enriched_table.copy()
    attrs = dict(enriched_table.attrs)

    for column_name, func in derived_columns.items():
        result = func(out)
        if isinstance(result, pd.Series):
            if len(result) != len(out):
                raise ValueError(
                    f"Derived column {column_name!r} returned a Series of "
                    "incorrect length."
                )
            if not result.index.equals(out.index):
                result = result.reindex(out.index)
            out[column_name] = result
        else:
            out[column_name] = result

    out.attrs.update(attrs)
    return out


# ---------------------------------------------------------------------------
# Stratification
# ---------------------------------------------------------------------------


def _sort_key_for_value(value: Any) -> tuple[int, str]:
    if pd.isna(value):
        return (1, "")
    return (0, str(value))


def _normalize_stratification_value(value: Any) -> Any:
    """Normalize values so explicit orders match dataframe values reliably."""
    if pd.isna(value):
        return "<NA>"
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (np.integer, int)) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, (np.floating, float)) and not isinstance(value, bool):
        return int(value) if float(value).is_integer() else float(value)
    return value


def _build_explicit_order_map(
    order_spec: Sequence[Any] | Mapping[Any, int] | None,
) -> dict[Any, int]:
    if order_spec is None:
        return {}

    if isinstance(order_spec, Mapping):
        items = list(order_spec.items())
    else:
        values = list(order_spec)
        normalized = [_normalize_stratification_value(value) for value in values]
        if len(set(normalized)) != len(normalized):
            raise ValueError("Duplicate values found in explicit stratification order.")
        items = [(value, index) for index, value in enumerate(values)]

    order_map: dict[Any, int] = {}
    for value, rank in items:
        key = _normalize_stratification_value(value)
        if key in order_map:
            raise ValueError("Duplicate values found in explicit stratification order.")
        order_map[key] = int(rank)

    return order_map


@dataclass
class StratificationSummary:
    variable: str
    levels: pd.DataFrame


@dataclass
class StratificationResult:
    table: pd.DataFrame
    summaries: list[StratificationSummary]
    stratification_variables: list[str]


def stratify_consistency_table(
    table: pd.DataFrame,
    variables: Sequence[str],
    *,
    variable_orders: Mapping[
        str,
        Sequence[Any] | Mapping[Any, int],
    ]
    | None = None,
) -> StratificationResult:
    """Assign a deterministic stratum identifier from selected variables."""
    if not variables:
        raise ValueError("At least one stratification variable is required.")

    missing = [variable for variable in variables if variable not in table.columns]
    if missing:
        raise KeyError(f"Variables not found in table: {missing}")

    variable_orders = variable_orders or {}
    out = table.copy()
    original_attrs = dict(table.attrs)
    summaries: list[StratificationSummary] = []
    code_parts: list[pd.Series] = []

    for variable in variables:
        normalized = out[variable].map(_normalize_stratification_value)
        counts = normalized.value_counts(dropna=False)
        levels = counts.rename_axis("value").reset_index(name="count")

        order_map = _build_explicit_order_map(variable_orders.get(variable))
        levels["_explicit_rank"] = levels["value"].map(
            lambda value, order_map=order_map: order_map.get(value, len(order_map))
        )
        levels["_fallback_rank"] = levels["value"].map(_sort_key_for_value)
        levels = (
            levels.sort_values(
                ["_explicit_rank", "_fallback_rank"],
                kind="stable",
            )
            .drop(columns=["_explicit_rank", "_fallback_rank"])
            .reset_index(drop=True)
        )

        summaries.append(
            StratificationSummary(variable=variable, levels=levels)
        )

        unique_values = levels["value"].tolist()
        mapping = {value: index for index, value in enumerate(unique_values)}
        mapped = normalized.map(mapping).astype("Int64")
        width = max(1, len(str(max(0, len(unique_values) - 1))))
        code_parts.append(
            mapped.map(lambda value, width=width: str(int(value)).zfill(width))
        )

    out["stratum_id"] = code_parts[0]
    for part in code_parts[1:]:
        out["stratum_id"] = out["stratum_id"].astype(str) + part.astype(str)

    out.attrs.update(original_attrs)
    return StratificationResult(
        table=out,
        summaries=summaries,
        stratification_variables=list(variables),
    )


# ---------------------------------------------------------------------------
# Proposal table
# ---------------------------------------------------------------------------


def _proposal_source_label(
    sources: set[str],
    *,
    dataset1_name: str = "dataset1",
    dataset2_name: str = "dataset2",
) -> str:
    source_set = {source for source in sources if source}
    if source_set == {"d1", "d2"}:
        return "both"
    if source_set == {"d1"}:
        return dataset1_name
    if source_set == {"d2"}:
        return dataset2_name
    if not source_set:
        return "none"
    return "+".join(sorted(source_set))


def _proposal_source_rank(sources: set[str]) -> tuple[int, str]:
    source_set = {source for source in sources if source}
    if source_set == {"d1", "d2"}:
        return (0, "both")
    if source_set == {"d1"}:
        return (1, "d1")
    if source_set == {"d2"}:
        return (2, "d2")
    if not source_set:
        return (3, "none")
    return (4, "+".join(sorted(source_set)))


def build_proposal_table(
    consistency_table: pd.DataFrame,
    sirene_df: pd.DataFrame,
    *,
    finess_df: pd.DataFrame,
    config: str | ReconciliationConfig | None = None,
    finess_entity_column: str | None = None,
    finess_business_id_column: str | None = None,
    sirene_business_id_column: str | None = None,
    sirene_columns: Sequence[str] | None = None,
    dataset1_name: str | None = None,
    dataset2_name: str | None = None,
    business_id_pad_to_length: int | None = None,
    # Backward-compatible EJ/SIREN keyword aliases:
    finess_ej_column: str | None = None,
    finess_siren_column: str | None = None,
    sirene_siren_column: str | None = None,
    siren_pad_to_length: int | None = None,
) -> pd.DataFrame:
    """Create one proposal row per unique entity/business-identifier pair.

    Output columns are configured by mode. EJ-SIREN produces ``EJ``,
    ``is_initial_siren`` and ``siren_proposal``. EGE-SIRET produces ``EGE``,
    ``is_initial_siret`` and ``siret_proposal``.
    """
    resolved = _resolve_config(config, consistency_table, sirene_df, finess_df)

    finess_entity_column = _coalesce_alias(
        finess_entity_column,
        finess_ej_column,
        generic_name="finess_entity_column",
        legacy_name="finess_ej_column",
    )
    finess_business_id_column = _coalesce_alias(
        finess_business_id_column,
        finess_siren_column,
        generic_name="finess_business_id_column",
        legacy_name="finess_siren_column",
    )
    sirene_business_id_column = _coalesce_alias(
        sirene_business_id_column,
        sirene_siren_column,
        generic_name="sirene_business_id_column",
        legacy_name="sirene_siren_column",
    )
    business_id_width = _coalesce_width_alias(
        business_id_pad_to_length,
        siren_pad_to_length,
        default=resolved.business_id_pad_width,
        generic_name="business_id_pad_to_length",
        legacy_name="siren_pad_to_length",
    )

    consistency_entity_column = _select_existing_column(
        consistency_table,
        explicit=None,
        candidates=(resolved.entity_column, _INTERNAL_ENTITY_COLUMN),
        label="consistency-table entity",
    )
    selected_finess_entity = _select_existing_column(
        finess_df,
        explicit=finess_entity_column,
        candidates=(resolved.entity_column, _INTERNAL_ENTITY_COLUMN),
        label="FINESS entity",
    )
    selected_finess_business = _select_existing_column(
        finess_df,
        explicit=finess_business_id_column,
        candidates=(resolved.business_id_column, _INTERNAL_BUSINESS_ID_COLUMN),
        label="FINESS business identifier",
    )
    selected_sirene_business = _select_existing_column(
        sirene_df,
        explicit=sirene_business_id_column,
        candidates=(resolved.business_id_column, _INTERNAL_BUSINESS_ID_COLUMN),
        label="SIRENE business identifier",
    )

    required_consistency_columns = {
        consistency_entity_column,
        "dataset1__proposals",
        "dataset2__proposals",
    }
    missing = required_consistency_columns - set(consistency_table.columns)
    if missing:
        raise KeyError(
            f"Consistency table is missing columns: {sorted(missing)}"
        )

    if dataset1_name is None:
        dataset1_name = consistency_table.attrs.get("dataset1_name", "dataset1")
    if dataset2_name is None:
        dataset2_name = consistency_table.attrs.get("dataset2_name", "dataset2")

    finess_base = finess_df.loc[
        :,
        [selected_finess_entity, selected_finess_business],
    ].rename(
        columns={
            selected_finess_entity: _INTERNAL_ENTITY_COLUMN,
            selected_finess_business: "initial_business_id",
        }
    )
    finess_base[_INTERNAL_ENTITY_COLUMN] = _normalize_key_series(
        finess_base[_INTERNAL_ENTITY_COLUMN],
        pad_to_length=resolved.entity_pad_width,
    )
    finess_base["initial_business_id"] = _normalize_key_series(
        finess_base["initial_business_id"],
        pad_to_length=business_id_width,
    )
    _require_non_null(
        finess_base[_INTERNAL_ENTITY_COLUMN],
        selected_finess_entity,
    )
    _ensure_unique(
        finess_base,
        [_INTERNAL_ENTITY_COLUMN],
        label="FINESS entity",
    )

    consistency_internal = consistency_table.rename(
        columns={consistency_entity_column: _INTERNAL_ENTITY_COLUMN}
    )
    dataset1_lookup = consistency_internal.set_index(_INTERNAL_ENTITY_COLUMN)[
        "dataset1__proposals"
    ].to_dict()
    dataset2_lookup = consistency_internal.set_index(_INTERNAL_ENTITY_COLUMN)[
        "dataset2__proposals"
    ].to_dict()

    proposal_rows: list[dict[str, Any]] = []
    proposal_column = resolved.business_id_proposal_column
    initial_flag_column = resolved.is_initial_business_id_column

    for row in finess_base.itertuples(index=False):
        entity_id = getattr(row, _INTERNAL_ENTITY_COLUMN)
        initial = row.initial_business_id
        proposals1 = _normalize_tuple_cell(dataset1_lookup.get(entity_id, ()))
        proposals2 = _normalize_tuple_cell(dataset2_lookup.get(entity_id, ()))

        sources_by_business_id: dict[str, set[str]] = defaultdict(set)
        for business_id in proposals1:
            normalized = _normalize_identifier(
                business_id,
                pad_to_length=business_id_width,
            )
            if normalized is not pd.NA:
                sources_by_business_id[str(normalized)].add("d1")
        for business_id in proposals2:
            normalized = _normalize_identifier(
                business_id,
                pad_to_length=business_id_width,
            )
            if normalized is not pd.NA:
                sources_by_business_id[str(normalized)].add("d2")

        if pd.isna(initial):
            proposal_rows.append(
                {
                    _INTERNAL_ENTITY_COLUMN: entity_id,
                    "candidate_rank": 1,
                    "proposal_source": "none",
                    initial_flag_column: True,
                    proposal_column: NO_INITIAL_BUSINESS_ID,
                }
            )
        else:
            initial_key = _normalize_identifier(
                initial,
                pad_to_length=business_id_width,
            )
            initial_text = str(initial_key)
            sources = sources_by_business_id.pop(initial_text, set())
            proposal_rows.append(
                {
                    _INTERNAL_ENTITY_COLUMN: entity_id,
                    "candidate_rank": 1,
                    "proposal_source": _proposal_source_label(
                        sources,
                        dataset1_name=dataset1_name,
                        dataset2_name=dataset2_name,
                    ),
                    initial_flag_column: True,
                    proposal_column: initial_text,
                }
            )

        remaining = sorted(
            sources_by_business_id.items(),
            key=lambda item: (_proposal_source_rank(item[1]), item[0]),
        )
        for rank, (business_id, sources) in enumerate(remaining, start=2):
            proposal_rows.append(
                {
                    _INTERNAL_ENTITY_COLUMN: entity_id,
                    "candidate_rank": rank,
                    "proposal_source": _proposal_source_label(
                        set(sources),
                        dataset1_name=dataset1_name,
                        dataset2_name=dataset2_name,
                    ),
                    initial_flag_column: False,
                    proposal_column: business_id,
                }
            )

    proposal_table = pd.DataFrame(proposal_rows)
    if proposal_table.empty:
        proposal_table = pd.DataFrame(
            columns=[
                _INTERNAL_ENTITY_COLUMN,
                "candidate_rank",
                "proposal_source",
                initial_flag_column,
                proposal_column,
            ]
        )

    selected_sirene_columns = [selected_sirene_business] + [
        column
        for column in (list(sirene_columns) if sirene_columns else [])
        if column != selected_sirene_business
    ]
    _require_columns(sirene_df, selected_sirene_columns, "SIRENE dataframe")
    sirene_selected = sirene_df.loc[:, selected_sirene_columns].copy()
    sirene_selected[selected_sirene_business] = _normalize_key_series(
        sirene_selected[selected_sirene_business],
        pad_to_length=business_id_width,
    )
    _require_non_null(
        sirene_selected[selected_sirene_business],
        selected_sirene_business,
    )
    _ensure_unique(
        sirene_selected,
        [selected_sirene_business],
        label="SIRENE business identifier",
    )
    sirene_selected = sirene_selected.rename(
        columns={
            column: f"sirene__{column}"
            for column in sirene_selected.columns
            if column != selected_sirene_business
        }
    )

    proposal_table = proposal_table.merge(
        sirene_selected,
        left_on=proposal_column,
        right_on=selected_sirene_business,
        how="left",
    ).drop(columns=[selected_sirene_business])

    consistency_for_merge = consistency_internal.copy()
    proposal_table = proposal_table.merge(
        consistency_for_merge,
        on=_INTERNAL_ENTITY_COLUMN,
        how="left",
    )
    proposal_table = proposal_table.rename(
        columns={_INTERNAL_ENTITY_COLUMN: resolved.entity_column}
    )

    proposal_table.attrs.update(consistency_table.attrs)
    return _attach_config(proposal_table, resolved)


__all__ = [
    "EGE_KEY_PAD_WIDTH",
    "EGE_SIRET_CONFIG",
    "EJ_KEY_PAD_WIDTH",
    "EJ_SIREN_CONFIG",
    "FINESS_ID_PAD_WIDTH",
    "NO_INITIAL_BUSINESS_ID",
    "NO_INITIAL_SIREN",
    "NO_INITIAL_SIRET",
    "SIREN_KEY_PAD_WIDTH",
    "SIRET_KEY_PAD_WIDTH",
    "ReconciliationConfig",
    "StratificationResult",
    "StratificationSummary",
    "apply_derived_columns",
    "build_consistency_table",
    "build_proposal_table",
    "compute_main_statistics",
    "enrich_consistency_table",
    "get_reconciliation_config",
    "load_ege_siret_dataset",
    "load_ej_siren_dataset",
    "load_finess_database",
    "load_reconciliation_dataset",
    "load_sirene_database",
    "load_sirene_database_for_identifiers",
    "stratify_consistency_table",
]
