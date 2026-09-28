"""Utilities for validating and consolidating reviewer annotations.

This module contains the responsibilities of workflow step ``04_merge_reviews``:

1. Load and validate per-stratum reviewer workbooks.
2. Optionally (and preferably) validate sampled entities against the proposal table.
3. Report non-blocking review-design deviations from the final strata plan.
4. Export reviewed sampled rows and one confirmed decision per reviewed entity.

Review analysis is intentionally kept in the separate ``analyze_reviews`` module.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

ENTITY_ID = "entity_id"
BUSINESS_ID = "business_id"
STRATUM_ID = "stratum_id"
UNCERTAINTY = "uncertainty"
COMMENT = "comment"
REVIEWER = "reviewer"

_SOURCE_FILE_COLUMN = "_source_file"
_VALID_EXCEL_SUFFIXES = {".xlsx", ".xlsm", ".xltx", ".xltm"}


class DataValidationError(ValueError):
    """Raised when an input file violates the expected schema or business rules."""


@dataclass(frozen=True)
class ReviewPipelineConfig:
    """Map public dataframe columns to the neutral review-validation model."""

    entity_name: str
    business_name: str
    entity_id_column: str
    reviewed_business_id_column: str
    business_id_length: int | None

    stratum_id_column: str = "stratum_id"
    uncertainty_column: str = "Incertitude1"
    comment_column: str = "Commentaire"
    reviewer_column: str = "reviewer"

    valid_business_id_specials: frozenset[str] = field(
        default_factory=lambda: frozenset({"NA", "N/A"})
    )
    valid_uncertainty_values: frozenset[str] = field(
        default_factory=lambda: frozenset({"-12", "-2", "-1", "0", "1", "2", "12"})
    )

    def __post_init__(self) -> None:
        public_columns = [
            self.entity_id_column,
            self.reviewed_business_id_column,
            self.stratum_id_column,
            self.uncertainty_column,
            self.comment_column,
            self.reviewer_column,
        ]
        duplicates = sorted(
            {name for name in public_columns if public_columns.count(name) > 1}
        )
        if duplicates:
            raise ValueError(
                f"Configured dataframe column names must be unique: {duplicates}"
            )
        if self.business_id_length is not None and self.business_id_length <= 0:
            raise ValueError("business_id_length must be a positive integer or None")

    @property
    def public_to_internal(self) -> Mapping[str, str]:
        return {
            self.entity_id_column: ENTITY_ID,
            self.reviewed_business_id_column: BUSINESS_ID,
            self.stratum_id_column: STRATUM_ID,
            self.uncertainty_column: UNCERTAINTY,
            self.comment_column: COMMENT,
            self.reviewer_column: REVIEWER,
        }

    @property
    def internal_to_public(self) -> Mapping[str, str]:
        return {
            internal: public for public, internal in self.public_to_internal.items()
        }

    @property
    def reviewer_columns(self) -> tuple[str, str, str]:
        return (
            self.reviewed_business_id_column,
            self.uncertainty_column,
            self.comment_column,
        )


EJ_SIREN_CONFIG = ReviewPipelineConfig(
    entity_name="EJ",
    business_name="siren",
    entity_id_column="EJ",
    reviewed_business_id_column="Siren_retenu",
    business_id_length=9,
)

EGE_SIRET_CONFIG = ReviewPipelineConfig(
    entity_name="EGE",
    business_name="siret",
    entity_id_column="EGE",
    reviewed_business_id_column="Siret_retenu",
    business_id_length=14,
)


@dataclass(frozen=True)
class LoadedStratumFile:
    path: Path
    stratum_id: str
    dataframe: pd.DataFrame


@dataclass(frozen=True)
class AdditionalDecisionMergeResult:
    """Result of combining current and supplementary confirmed decisions."""

    combined_decisions: pd.DataFrame
    additional_decisions: pd.DataFrame
    identical_overlaps: list[str]
    conflicting_overlaps: list[str]
    additional_only_entities: list[str]


def _emit_notice(message: str) -> None:
    """Display a readable validation/reporting message."""

    print(f"Warning: {message}")

def _short_label(source: str | Path) -> str:
    """Return a compact label suitable for messages."""

    return Path(source).name

def _canonical_text(value) -> str | None:
    """Return a stripped string or None for missing values."""

    if pd.isna(value):
        return None
    text = str(value).strip()
    return text if text != "" else None

def _effective_uncertainty_values(
    values: Iterable,
    *,
    default_empty_to_zero: bool = False,
) -> list[str]:
    """Return explicit uncertainty values, optionally defaulting an empty group to ``"0"``.

    Empty uncertainty cells are ignored when another candidate row contains an
    explicit value. An entirely empty uncertainty group behaves like ``0`` only
    when the entity has another reviewer action, namely a retained business id
    or a comment. Untouched entities therefore remain unreviewed.
    """

    explicit_values = _non_empty_texts(values)
    if explicit_values:
        return explicit_values
    return ["0"] if default_empty_to_zero else []

def _canonical_identifier(value) -> str | None:
    """Canonicalize identifiers without altering their visible digits."""

    return _canonical_text(value)

def _non_empty_texts(values: Iterable) -> list[str]:
    """Return distinct non-empty canonical text values in input order."""

    texts: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _canonical_text(value)
        if text is None or text in seen:
            continue
        seen.add(text)
        texts.append(text)
    return texts

def _format_entity_list(entities: Iterable) -> str:
    unique: list[str] = []
    seen: set[str] = set()
    for entity in entities:
        entity_text = _canonical_identifier(entity)
        if entity_text is None or entity_text in seen:
            continue
        seen.add(entity_text)
        unique.append(entity_text)
    return ", ".join(sorted(unique))

def _format_grouped_entities(grouped: dict[str | None, Iterable]) -> str:
    """Format entity identifiers grouped by stratum."""

    parts: list[str] = []
    for stratum_id in sorted(grouped.keys(), key=lambda v: "" if v is None else str(v)):
        entities = _format_entity_list(grouped[stratum_id])
        if not entities:
            continue
        label = _canonical_identifier(stratum_id) or "<missing stratum>"
        parts.append(f"stratum {label}: {entities}")
    return "; ".join(parts)

def _format_grouped_strata_by_reviewer(grouped: dict[str | None, Iterable[str]]) -> str:
    """Format missing strata grouped by reviewer."""

    parts: list[str] = []
    for reviewer in sorted(grouped.keys(), key=lambda v: "" if v is None else str(v)):
        stratum_ids = sorted(
            {
                _canonical_identifier(stratum_id) or "<missing stratum>"
                for stratum_id in grouped[reviewer]
            }
        )
        if not stratum_ids:
            continue
        label = _canonical_text(reviewer) or "<missing reviewer>"
        parts.append(f"reviewer {label}: {', '.join(stratum_ids)}")
    return "; ".join(parts)

def _raise_if_missing_columns(df: pd.DataFrame, columns: Sequence[str], *, source: str) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise DataValidationError(f"{source}: missing required columns: {missing}")

def _to_internal(
    df: pd.DataFrame,
    config: ReviewPipelineConfig,
    *,
    required_internal: Sequence[str] = (),
    source: str = "dataframe",
) -> pd.DataFrame:
    """Copy a public dataframe and rename configured columns to neutral names."""

    required_public = [config.internal_to_public[name] for name in required_internal]
    _raise_if_missing_columns(df, required_public, source=source)

    rename_map = {
        public: internal
        for public, internal in config.public_to_internal.items()
        if public in df.columns and public != internal
    }
    collisions = sorted(
        internal
        for public, internal in rename_map.items()
        if internal in df.columns and internal != public
    )
    if collisions:
        raise DataValidationError(
            f"{source}: neutral internal column name collision(s): {collisions}. "
            "Rename the unrelated source columns or adjust the configuration."
        )
    return df.copy().rename(columns=rename_map)

def _to_public(df: pd.DataFrame, config: ReviewPipelineConfig) -> pd.DataFrame:
    """Copy an internal dataframe and restore configured public column names."""

    rename_map = {
        internal: public
        for internal, public in config.internal_to_public.items()
        if internal in df.columns and internal != public
    }
    collisions = sorted(
        public
        for internal, public in rename_map.items()
        if public in df.columns and public != internal
    )
    if collisions:
        raise DataValidationError(
            f"Cannot restore configured public columns because they already exist: {collisions}"
        )
    return df.copy().rename(columns=rename_map)

def _valid_business_identifier(value: str, config: ReviewPipelineConfig) -> bool:
    if value in config.valid_business_id_specials:
        return True
    if config.business_id_length is None:
        return bool(re.fullmatch(r"\d+", value))
    return bool(re.fullmatch(rf"\d{{{config.business_id_length}}}", value))

def _validate_reviewer_rules(
    df: pd.DataFrame,
    *,
    config: ReviewPipelineConfig,
    source: str,
) -> None:
    """Validate reviewer columns and block contradictory or invalid decisions.

    Order gaps and sampling deviations are reported separately by
    :func:`report_review_design_deviations`. This function concerns decision
    validity only: a contradictory value,
    malformed retained identifier, invalid uncertainty code, or a sure decision
    without a retained identifier must be corrected before an authoritative
    confirmed database can be created.
    """

    working = _to_internal(
        df,
        config,
        required_internal=(ENTITY_ID, STRATUM_ID, BUSINESS_ID, UNCERTAINTY, COMMENT),
        source=source,
    )

    working["_entity_id_norm"] = working[ENTITY_ID].map(_canonical_identifier)
    working["_stratum_id_norm"] = working[STRATUM_ID].map(_canonical_identifier)
    working["_business_id_norm"] = working[BUSINESS_ID].map(_canonical_text)
    working["_uncertainty_norm"] = working[UNCERTAINTY].map(_canonical_text)
    working["_comment_norm"] = working[COMMENT].map(_canonical_text)

    inconsistent_by_stratum: dict[str | None, list[str]] = defaultdict(list)
    invalid_business_by_stratum: dict[str | None, list[str]] = defaultdict(list)
    invalid_uncertainty_by_stratum: dict[str | None, list[str]] = defaultdict(list)
    uncertainty_without_business_by_stratum: dict[str | None, list[str]] = defaultdict(list)
    business_equals_entity_by_stratum: dict[str | None, list[str]] = defaultdict(list)

    for entity_id, group in working.groupby("_entity_id_norm", dropna=False, sort=False):
        if entity_id is None:
            continue

        stratum_values = _non_empty_texts(group["_stratum_id_norm"].tolist())
        stratum_ids = stratum_values if stratum_values else [None]

        business_values = [v for v in group["_business_id_norm"].tolist() if pd.notna(v)]
        has_comment = bool(_non_empty_texts(group["_comment_norm"].tolist()))
        uncertainty_values = _effective_uncertainty_values(
            group["_uncertainty_norm"].tolist(),
            default_empty_to_zero=bool(business_values) or has_comment,
        )

        distinct_business_values = list(dict.fromkeys(business_values))
        distinct_uncertainty_values = list(dict.fromkeys(uncertainty_values))

        if len(distinct_business_values) > 1 or len(distinct_uncertainty_values) > 1:
            for stratum_id in stratum_ids:
                inconsistent_by_stratum[stratum_id].append(entity_id)
            continue

        if distinct_business_values:
            business_text = distinct_business_values[0]
            if not _valid_business_identifier(business_text, config):
                for stratum_id in stratum_ids:
                    invalid_business_by_stratum[stratum_id].append(entity_id)

            if business_text == entity_id:
                for stratum_id in stratum_ids:
                    business_equals_entity_by_stratum[stratum_id].append(entity_id)

        if distinct_uncertainty_values:
            uncertainty_text = distinct_uncertainty_values[0]
            if uncertainty_text not in config.valid_uncertainty_values:
                for stratum_id in stratum_ids:
                    invalid_uncertainty_by_stratum[stratum_id].append(entity_id)

        has_business = bool(distinct_business_values)
        has_zero_uncertainty = "0" in distinct_uncertainty_values

        if (not has_business) and has_zero_uncertainty:
            for stratum_id in stratum_ids:
                uncertainty_without_business_by_stratum[stratum_id].append(entity_id)


    entity_label = config.entity_name
    business_column = config.reviewed_business_id_column
    uncertainty_column = config.uncertainty_column

    blocking_messages: list[str] = []

    if inconsistent_by_stratum:
        blocking_messages.append(
            f"{_short_label(source)}: {business_column} and {uncertainty_column} contain multiple "
            f"distinct values across rows for {entity_label}s: "
            f"{_format_grouped_entities(inconsistent_by_stratum)}"
        )

    if invalid_business_by_stratum:
        if config.business_id_length is None:
            allowed = "a numeric string"
        else:
            allowed = f"a {config.business_id_length}-digit numeric string"
        specials = ", ".join(repr(value) for value in sorted(config.valid_business_id_specials))
        blocking_messages.append(
            f"{_short_label(source)}: invalid {business_column} values. Allowed values are {allowed} "
            f"or {specials}. Affected {entity_label}s: "
            f"{_format_grouped_entities(invalid_business_by_stratum)}"
        )

    if invalid_uncertainty_by_stratum:
        allowed = ", ".join(repr(value) for value in sorted(config.valid_uncertainty_values))
        blocking_messages.append(
            f"{_short_label(source)}: invalid {uncertainty_column} values. Allowed values are {allowed}. "
            f"Affected {entity_label}s: {_format_grouped_entities(invalid_uncertainty_by_stratum)}"
        )

    if uncertainty_without_business_by_stratum:
        blocking_messages.append(
            f"{_short_label(source)}: {uncertainty_column} is 0 or empty without a retained "
            f"{config.business_name}; an explicit retained identifier or valid closure/intervention "
            f"decision is required. "
            f"Affected {entity_label}s: "
            f"{_format_grouped_entities(uncertainty_without_business_by_stratum)}"
        )

    if business_equals_entity_by_stratum:
        _emit_notice(
            f"{_short_label(source)}: {business_column} matches {config.entity_id_column}. "
            f"Affected {entity_label}s: "
            f"{_format_grouped_entities(business_equals_entity_by_stratum)}"
        )

    if blocking_messages:
        raise DataValidationError(
            "Blocking reviewer-decision corrections are required before the confirmed "
            "database can be created:\n - " + "\n - ".join(blocking_messages)
        )

def _validate_stratum_filename(path: Path) -> str:
    """Return the six-digit stratum id encoded in the filename, or raise."""

    match = re.fullmatch(r"(\d{6})__.+", path.stem)
    if not match:
        raise DataValidationError(f"Unexpected stratum filename format: {path}")
    return match.group(1)

def _read_excel_as_strings(path: Path, *, sheet_name=0) -> pd.DataFrame:
    return pd.read_excel(path, sheet_name=sheet_name, dtype=str, keep_default_na=False)

def _read_parquet(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)

def load_stratum_files(
    results_root: str | Path,
    *,
    config: ReviewPipelineConfig = EJ_SIREN_CONFIG,
    correction_report_path: str | Path | None = None,
) -> tuple[pd.DataFrame, list[LoadedStratumFile]]:
    """Load, validate, and concatenate all stratum XLSX files recursively.

    When ``correction_report_path`` is supplied, all workbook-level blocking
    errors are collected into an actionable CSV before the function raises.  An
    empty report is written on success so automation can distinguish "no issues"
    from "validation was not run".
    """

    root = Path(results_root)
    if not root.exists():
        raise FileNotFoundError(f"Stratum results directory not found: {root}")

    xlsx_paths = sorted(
        path for path in root.rglob("*.xlsx") if not path.name.startswith("~$")
    )

    loaded: list[LoadedStratumFile] = []
    frames: list[pd.DataFrame] = []
    corrections: list[dict[str, str]] = []

    required_columns = (
        config.entity_id_column,
        config.stratum_id_column,
        *config.reviewer_columns,
    )

    for path in xlsx_paths:
        try:
            expected_stratum_id = _validate_stratum_filename(path)
            df = _read_excel_as_strings(path)
            _raise_if_missing_columns(df, required_columns, source=str(path))

            file_strata = {
                _canonical_identifier(value)
                for value in df[config.stratum_id_column].tolist()
                if _canonical_identifier(value) is not None
            }
            if file_strata != {expected_stratum_id}:
                raise DataValidationError(
                    f"{path}: {config.stratum_id_column} values do not match the filename stratum id "
                    f"{expected_stratum_id}. Found: {sorted(file_strata)}"
                )

            _validate_reviewer_rules(df, config=config, source=path.name)
        except (DataValidationError, ValueError) as error:
            corrections.append(
                {
                    "source_file": str(path),
                    "entity_type": config.entity_name,
                    "blocking_reason": str(error),
                    "required_action": "Correct the source workbook and rerun Stage 04.",
                }
            )
            continue

        public_df = df.copy()
        public_df[_SOURCE_FILE_COLUMN] = str(path)
        loaded.append(
            LoadedStratumFile(path=path, stratum_id=expected_stratum_id, dataframe=public_df)
        )
        frames.append(public_df)

    combined = pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()

    if not combined.empty:
        normalized_entities = combined[config.entity_id_column].map(
            _canonical_identifier
        )
        entity_file_counts = (
            combined.assign(_entity_id_norm=normalized_entities)
            .dropna(subset=["_entity_id_norm"])
            .groupby("_entity_id_norm", sort=False)[_SOURCE_FILE_COLUMN]
            .nunique()
        )
        cross_workbook_entities = entity_file_counts[
            entity_file_counts.gt(1)
        ].index.tolist()
        if cross_workbook_entities:
            corrections.append(
                {
                    "source_file": "<multiple review workbooks>",
                    "entity_type": config.entity_name,
                    "blocking_reason": (
                        f"{config.entity_name} values appear in more than one review "
                        f"workbook: {cross_workbook_entities[:20]}"
                    ),
                    "required_action": (
                        "Keep each entity in exactly one completed review workbook "
                        "and rerun Stage 04."
                    ),
                }
            )

    correction_columns = [
        "source_file",
        "entity_type",
        "blocking_reason",
        "required_action",
    ]
    if correction_report_path is not None:
        report_path = Path(correction_report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame.from_records(corrections, columns=correction_columns).to_csv(
            report_path, index=False, encoding="utf-8-sig"
        )

    if corrections:
        report_note = (
            f" See correction report: {Path(correction_report_path)}"
            if correction_report_path is not None
            else ""
        )
        raise DataValidationError(
            f"{len(corrections)} review-consolidation blocking issue(s) found."
            f"{report_note}"
        )

    return combined, loaded

def load_proposal_table(
    proposal_path: str | Path,
    *,
    config: ReviewPipelineConfig = EJ_SIREN_CONFIG,
) -> pd.DataFrame:
    """Load the proposal table used to validate sampled entities and strata.

    Only the configured entity id and stratum id columns are required. Excel and
    parquet inputs are supported so the validation can be added without changing
    the proposal-generation format.
    """

    path = Path(proposal_path)
    if not path.exists():
        raise FileNotFoundError(f"Proposal table not found: {path}")

    suffix = path.suffix.lower()
    if suffix in _VALID_EXCEL_SUFFIXES:
        df = _read_excel_as_strings(path)
    elif suffix == ".parquet":
        df = _read_parquet(path)
    else:
        raise DataValidationError(
            f"Unsupported proposal-table format for {path.name!r}; expected Excel or parquet"
        )

    _raise_if_missing_columns(
        df,
        (config.entity_id_column, config.stratum_id_column),
        source=str(path),
    )
    return df

def validate_stratum_entities_against_proposals(
    stratum_df: pd.DataFrame,
    proposal_df: pd.DataFrame,
    *,
    config: ReviewPipelineConfig = EGE_SIRET_CONFIG,
    source: str = "proposal_df",
) -> None:
    """Check that sampled entities exist in the proposal table with the right stratum.

    The check is optional at pipeline level, but recommended. When supplied, the
    proposal table is treated as the reference for entity membership and stratum
    assignment. Any missing entity, ambiguous proposal stratum, or stratum mismatch
    raises :class:`DataValidationError`.
    """

    if stratum_df.empty:
        return

    review = _to_internal(
        stratum_df,
        config,
        required_internal=(ENTITY_ID, STRATUM_ID),
        source="stratum_df",
    )
    proposals = _to_internal(
        proposal_df,
        config,
        required_internal=(ENTITY_ID, STRATUM_ID),
        source=source,
    )

    review["_entity_id_norm"] = review[ENTITY_ID].map(_canonical_identifier)
    review["_stratum_id_norm"] = review[STRATUM_ID].map(_canonical_identifier)
    proposals["_entity_id_norm"] = proposals[ENTITY_ID].map(_canonical_identifier)
    proposals["_stratum_id_norm"] = proposals[STRATUM_ID].map(_canonical_identifier)

    proposal_strata: dict[str, set[str]] = defaultdict(set)
    for entity_id, stratum_id in proposals[["_entity_id_norm", "_stratum_id_norm"]].itertuples(
        index=False, name=None
    ):
        if entity_id is None:
            continue
        if stratum_id is not None:
            proposal_strata[entity_id].add(stratum_id)
        else:
            proposal_strata.setdefault(entity_id, set())

    reviewed_entities = [
        entity_id
        for entity_id in review["_entity_id_norm"].dropna().drop_duplicates().tolist()
    ]
    missing_entities = [entity_id for entity_id in reviewed_entities if entity_id not in proposal_strata]
    missing_entity_set = set(missing_entities)
    missing_entities_by_stratum: dict[str | None, list[str]] = defaultdict(list)
    for entity_id, review_stratum in review[["_entity_id_norm", "_stratum_id_norm"]].drop_duplicates().itertuples(
        index=False, name=None
    ):
        if entity_id is not None and entity_id in missing_entity_set:
            missing_entities_by_stratum[review_stratum].append(entity_id)

    ambiguous_entities = {
        entity_id: strata
        for entity_id, strata in proposal_strata.items()
        if entity_id in set(reviewed_entities) and len(strata) != 1
    }

    mismatches: list[tuple[str, str | None, str]] = []
    for entity_id, review_stratum in review[["_entity_id_norm", "_stratum_id_norm"]].drop_duplicates().itertuples(
        index=False, name=None
    ):
        if entity_id is None or entity_id in missing_entities or entity_id in ambiguous_entities:
            continue
        expected_stratum = next(iter(proposal_strata[entity_id]))
        if review_stratum != expected_stratum:
            mismatches.append((entity_id, review_stratum, expected_stratum))

    problems: list[str] = []
    if missing_entities_by_stratum:
        problems.append(
            f"{config.entity_name}s absent from the proposal table, grouped by review stratum: "
            f"{_format_grouped_entities(missing_entities_by_stratum)}"
        )
    if ambiguous_entities:
        details = "; ".join(
            f"{entity_id}: {', '.join(sorted(strata)) if strata else '<missing stratum>'}"
            for entity_id, strata in sorted(ambiguous_entities.items())
        )
        problems.append(
            f"{config.entity_name}s without exactly one proposal stratum: {details}"
        )
    if mismatches:
        details = "; ".join(
            f"{entity_id}: review={review_stratum or '<missing>'}, proposal={expected_stratum}"
            for entity_id, review_stratum, expected_stratum in sorted(mismatches)
        )
        problems.append(f"incorrect {config.stratum_id_column}: {details}")

    if problems:
        raise DataValidationError(
            f"Proposal-table validation failed against {_short_label(source)}. " + " | ".join(problems)
        )

def load_strata_plan(
    plan_path: str | Path,
    *,
    config: ReviewPipelineConfig = EJ_SIREN_CONFIG,
) -> pd.DataFrame:
    """Load the strata plan workbook with all columns as strings."""

    path = Path(plan_path)
    if not path.exists():
        raise FileNotFoundError(f"Strata plan workbook not found: {path}")

    df = _read_excel_as_strings(path)
    _raise_if_missing_columns(
        df,
        (config.stratum_id_column, config.reviewer_column),
        source=str(path),
    )
    return df

def _review_status(
    group: pd.DataFrame,
    *,
    config: ReviewPipelineConfig,
) -> dict[str, object]:
    """Summarize whether an internal entity group is reviewed and why."""

    business_values = _non_empty_texts(group[BUSINESS_ID].tolist())
    comment_values = _non_empty_texts(group[COMMENT].tolist())

    has_business = bool(business_values)
    has_comment = bool(comment_values)
    uncertainty_values = _effective_uncertainty_values(
        group[UNCERTAINTY].tolist(),
        default_empty_to_zero=has_business or has_comment,
    )
    has_valid_uncertainty = any(
        value in config.valid_uncertainty_values for value in uncertainty_values
    )

    reviewed = has_business or has_comment or has_valid_uncertainty

    return {
        "reviewed": reviewed,
        "has_business": has_business,
        "has_comment": has_comment,
        "effective_uncertainty_values": uncertainty_values,
    }

def _reviewed_mask(
    df: pd.DataFrame,
    *,
    config: ReviewPipelineConfig,
) -> pd.Series:
    """Return a boolean mask marking reviewed entity groups in a public dataframe."""

    if df.empty:
        return pd.Series(dtype=bool, index=df.index)

    internal = _to_internal(
        df,
        config,
        required_internal=(ENTITY_ID, BUSINESS_ID, UNCERTAINTY, COMMENT),
        source="df",
    )

    reviewed_entities: set[str] = set()
    normalized_entity = internal[ENTITY_ID].map(_canonical_identifier)
    for entity_id, group in internal.groupby(normalized_entity, dropna=False, sort=False):
        if entity_id is None:
            continue
        if _review_status(group, config=config)["reviewed"]:
            reviewed_entities.add(entity_id)

    return normalized_entity.isin(reviewed_entities)

def filter_reviewed_cases(
    df: pd.DataFrame,
    *,
    config: ReviewPipelineConfig = EJ_SIREN_CONFIG,
) -> pd.DataFrame:
    """Return a public dataframe keeping only reviewed entity cases.

    A case is reviewed when it has a retained business id, a comment, or an
    explicit valid uncertainty value. An entirely empty uncertainty decision
    behaves like ``0`` only when a retained business id or comment is present.
    """

    public_df = df.drop(columns=[_SOURCE_FILE_COLUMN], errors="ignore")
    if public_df.empty:
        return public_df.copy()
    return public_df.loc[_reviewed_mask(public_df, config=config)].copy()

def report_missing_strata(
    *,
    plan_df: pd.DataFrame | None,
    stratum_df: pd.DataFrame,
    config: ReviewPipelineConfig,
) -> list[str]:
    """Return and report planned strata for which no file was loaded."""

    if plan_df is None or plan_df.empty:
        return []

    plan = _to_internal(
        plan_df,
        config,
        required_internal=(STRATUM_ID, REVIEWER),
        source="plan_df",
    )
    plan["_stratum_id_norm"] = plan[STRATUM_ID].map(_canonical_identifier)

    planned_mask = plan["_stratum_id_norm"].notna()
    prefix = "Planned strata with no matching file were found: "

    planned_strata = set(plan.loc[planned_mask, "_stratum_id_norm"].dropna())

    if stratum_df.empty or config.stratum_id_column not in stratum_df.columns:
        loaded_strata: set[str] = set()
    else:
        loaded_strata = {
            normalized
            for value in stratum_df[config.stratum_id_column].tolist()
            if (normalized := _canonical_identifier(value)) is not None
        }

    missing_strata = sorted(planned_strata - loaded_strata)
    if not missing_strata:
        return []

    missing_by_reviewer: dict[str | None, list[str]] = defaultdict(list)
    missing_mask = planned_mask & plan["_stratum_id_norm"].isin(missing_strata)
    for _, row in plan.loc[missing_mask, [REVIEWER, STRATUM_ID]].iterrows():
        missing_by_reviewer[_canonical_text(row[REVIEWER])].append(
            _canonical_identifier(row[STRATUM_ID]) or "<missing stratum>"
        )
    _emit_notice(prefix + _format_grouped_strata_by_reviewer(missing_by_reviewer))
    return missing_strata

def report_review_design_deviations(
    *,
    plan_df: pd.DataFrame | None,
    stratum_df: pd.DataFrame,
    config: ReviewPipelineConfig,
    sample_size_column: str = "sample_size",
) -> dict[str, list[dict[str, object]]]:
    """Report non-blocking deviations between planned and realised review.

    The final strata plan supplies the reference ``sample_size``.  The realised
    review count uses the same entity-level rule as :func:`filter_reviewed_cases`.
    A shortfall is reported as a notice. An ordered extension is acceptable and
    remains available in the returned diagnostics without producing a warning.
    An internal gap is also non-blocking, but is reported separately because one
    or more untouched entities occur before the last reviewed entity in the
    deterministic workbook order.
    """

    diagnostics: dict[str, list[dict[str, object]]] = {
        "review_shortfalls": [],
        "review_extensions": [],
        "internal_review_gaps": [],
    }

    if plan_df is None or plan_df.empty:
        return diagnostics

    if sample_size_column not in plan_df.columns:
        raise DataValidationError(
            f"plan_df: missing required column: {sample_size_column!r}"
        )

    plan = _to_internal(
        plan_df,
        config,
        required_internal=(STRATUM_ID, REVIEWER),
        source="plan_df",
    )
    plan["_stratum_id_norm"] = plan[STRATUM_ID].map(_canonical_identifier)
    if plan["_stratum_id_norm"].isna().any():
        raise DataValidationError("plan_df: missing stratum identifiers")
    if plan["_stratum_id_norm"].duplicated().any():
        duplicates = sorted(
            set(plan.loc[plan["_stratum_id_norm"].duplicated(False), "_stratum_id_norm"])
        )
        raise DataValidationError(
            "plan_df must contain one row per stratum; duplicates: "
            + ", ".join(duplicates)
        )

    sample_sizes = pd.to_numeric(plan_df[sample_size_column], errors="coerce")
    invalid_sample_sizes = (
        sample_sizes.isna()
        | sample_sizes.lt(0)
        | sample_sizes.mod(1).ne(0)
    )
    if invalid_sample_sizes.any():
        bad = plan_df.loc[
            invalid_sample_sizes,
            [config.stratum_id_column, sample_size_column],
        ].head(10).to_dict("records")
        raise DataValidationError(
            f"plan_df[{sample_size_column!r}] must contain non-negative integers. "
            f"Invalid values: {bad}"
        )
    plan["_sample_size"] = sample_sizes.astype("int64").to_numpy()

    plan_by_stratum = plan.set_index("_stratum_id_norm", drop=False)

    if stratum_df.empty:
        return diagnostics

    reviewed_mask = _reviewed_mask(stratum_df, config=config)
    reviewed_rows = stratum_df.loc[reviewed_mask].copy()

    if reviewed_rows.empty:
        reviewed_counts: dict[str, int] = {}
    else:
        reviewed_internal = _to_internal(
            reviewed_rows,
            config,
            required_internal=(ENTITY_ID, STRATUM_ID),
            source="stratum_df",
        )
        reviewed_internal["_entity_id_norm"] = reviewed_internal[ENTITY_ID].map(
            _canonical_identifier
        )
        reviewed_internal["_stratum_id_norm"] = reviewed_internal[STRATUM_ID].map(
            _canonical_identifier
        )
        reviewed_counts = (
            reviewed_internal.dropna(
                subset=["_entity_id_norm", "_stratum_id_norm"]
            )
            .groupby("_stratum_id_norm", sort=False)["_entity_id_norm"]
            .nunique()
            .astype(int)
            .to_dict()
        )

    loaded_internal = _to_internal(
        stratum_df,
        config,
        required_internal=(STRATUM_ID,),
        source="stratum_df",
    )
    loaded_strata = {
        normalized
        for value in loaded_internal[STRATUM_ID].tolist()
        if (normalized := _canonical_identifier(value)) is not None
    }

    for stratum_id in sorted(loaded_strata):
        if stratum_id not in plan_by_stratum.index:
            continue
        plan_row = plan_by_stratum.loc[stratum_id]
        planned = int(plan_row["_sample_size"])
        reviewed = int(reviewed_counts.get(stratum_id, 0))
        reviewer = _canonical_text(plan_row[REVIEWER])

        record = {
            "stratum_id": stratum_id,
            "reviewer": reviewer,
            "planned_sample_size": planned,
            "reviewed_entities": reviewed,
            "difference": reviewed - planned,
        }
        if reviewed < planned:
            diagnostics["review_shortfalls"].append(record)
        elif reviewed > planned:
            diagnostics["review_extensions"].append(record)

    if diagnostics["review_shortfalls"]:
        details = "; ".join(
            f"stratum {item['stratum_id']}: planned {item['planned_sample_size']}, "
            f"reviewed {item['reviewed_entities']}"
            for item in diagnostics["review_shortfalls"]
        )
        _emit_notice("Review sample shortfalls: " + details)

    source_groups: Iterable[tuple[object, pd.DataFrame]]
    if _SOURCE_FILE_COLUMN in stratum_df.columns:
        source_groups = stratum_df.groupby(_SOURCE_FILE_COLUMN, sort=False, dropna=False)
    else:
        source_groups = [("<combined review>", stratum_df)]

    for source_file, file_df in source_groups:
        internal = _to_internal(
            file_df,
            config,
            required_internal=(ENTITY_ID, STRATUM_ID, BUSINESS_ID, UNCERTAINTY, COMMENT),
            source=str(source_file),
        )
        internal["_entity_id_norm"] = internal[ENTITY_ID].map(_canonical_identifier)
        internal["_stratum_id_norm"] = internal[STRATUM_ID].map(_canonical_identifier)

        stratum_values = _non_empty_texts(internal["_stratum_id_norm"].tolist())
        stratum_id = stratum_values[0] if stratum_values else None
        reviewer = (
            _canonical_text(plan_by_stratum.loc[stratum_id, REVIEWER])
            if stratum_id in plan_by_stratum.index
            else None
        )

        sequence: list[tuple[str, bool]] = []
        for entity_id, group in internal.groupby(
            "_entity_id_norm", dropna=False, sort=False
        ):
            if entity_id is None or pd.isna(entity_id):
                continue
            sequence.append(
                (str(entity_id), bool(_review_status(group, config=config)["reviewed"]))
            )

        reviewed_indices = [
            index
            for index, (_, reviewed) in enumerate(sequence)
            if reviewed
        ]
        if not reviewed_indices:
            continue

        last_reviewed_index = reviewed_indices[-1]
        unreviewed_gap_entities = [
            entity_id
            for entity_id, reviewed in sequence[:last_reviewed_index]
            if not reviewed
        ]
        if not unreviewed_gap_entities:
            continue

        gap_record = {
            "stratum_id": stratum_id,
            "reviewer": reviewer,
            "source_file": str(source_file),
            "unreviewed_gap_entities": unreviewed_gap_entities,
            "gap_count": len(unreviewed_gap_entities),
        }
        diagnostics["internal_review_gaps"].append(gap_record)

        preview = ", ".join(unreviewed_gap_entities[:10])
        suffix = " ..." if len(unreviewed_gap_entities) > 10 else ""
        _emit_notice(
            "Internal review gap: "
            f"stratum {stratum_id or '<missing>'}, "
            f"reviewer {reviewer or '<missing reviewer>'}; "
            f"unreviewed {config.entity_name}(s) within the reviewed prefix: "
            f"{preview}{suffix}"
        )

    return diagnostics


def _selected_reviewer_row(
    group: pd.DataFrame,
    *,
    config: ReviewPipelineConfig,
) -> pd.Series | None:
    """Return the row carrying the selected reviewer decision."""

    business_mask = group[BUSINESS_ID].map(_canonical_text).notna()
    if business_mask.any():
        return group.loc[business_mask].iloc[0]

    explicit_uncertainty = group[UNCERTAINTY].map(_canonical_text)
    uncertainty_mask = explicit_uncertainty.isin(config.valid_uncertainty_values)
    if uncertainty_mask.any():
        return group.loc[uncertainty_mask].iloc[0]

    comment_mask = group[COMMENT].map(_canonical_text).notna()
    if comment_mask.any():
        return group.loc[comment_mask].iloc[0]
    return None

def _selected_review_decision(
    group: pd.DataFrame,
    *,
    config: ReviewPipelineConfig,
) -> dict[str, str | None] | None:
    """Return the selected neutral reviewer decision for one reviewed entity."""

    review_status = _review_status(group, config=config)
    if not review_status["reviewed"]:
        return None

    selected_row = _selected_reviewer_row(group, config=config)
    if selected_row is None:
        return None

    selected_business = _canonical_text(selected_row[BUSINESS_ID])
    effective_uncertainty_values = review_status["effective_uncertainty_values"]
    selected_uncertainty = (
        effective_uncertainty_values[0] if effective_uncertainty_values else None
    )
    if not review_status["has_business"]:
        selected_business = "NA"

    return {
        BUSINESS_ID: selected_business,
        UNCERTAINTY: selected_uncertainty,
        COMMENT: _canonical_text(selected_row[COMMENT]),
    }

def build_confirmed_database(
    df: pd.DataFrame,
    *,
    config: ReviewPipelineConfig = EJ_SIREN_CONFIG,
) -> pd.DataFrame:
    """Return one selected reviewer decision per reviewed entity.

    The returned dataframe uses the configured real/public column names.
    """

    internal = _to_internal(
        df,
        config,
        required_internal=(ENTITY_ID, BUSINESS_ID, UNCERTAINTY, COMMENT),
        source="df",
    )

    records: list[dict[str, str | None]] = []
    normalized_entities = internal[ENTITY_ID].map(_canonical_identifier)
    for entity_id, group in internal.groupby(
        normalized_entities, dropna=False, sort=False
    ):
        if entity_id is None:
            continue
        decision = _selected_review_decision(group, config=config)
        if decision is None:
            continue
        records.append({ENTITY_ID: entity_id, **decision})

    confirmed_internal = pd.DataFrame.from_records(
        records,
        columns=[ENTITY_ID, BUSINESS_ID, UNCERTAINTY, COMMENT],
    )
    return _to_public(confirmed_internal, config)


def _canonical_spreadsheet_text(value) -> str | None:
    """Normalize spreadsheet-like scalar text for confirmed-decision comparisons."""
    text = _canonical_text(value)
    if text is None:
        return None
    if re.fullmatch(r"[+-]?\d+\.0+", text):
        return text.split(".", 1)[0]
    return text


def validate_confirmed_decision_table(
    df: pd.DataFrame,
    *,
    config: ReviewPipelineConfig,
    source: str,
) -> pd.DataFrame:
    """Validate one-row-per-entity confirmed decisions and return public columns.

    This helper is intentionally structural: the direct review consolidation has
    already validated reviewer decision rules. It is used for supplementary decision
    inputs before they are combined with the current consolidated decisions.
    """
    required = [
        config.entity_id_column,
        config.reviewed_business_id_column,
        config.uncertainty_column,
        config.comment_column,
    ]
    _raise_if_missing_columns(df, required, source=source)

    validated = df.loc[:, required].copy()
    normalized_entities = validated[config.entity_id_column].map(
        _canonical_spreadsheet_text
    )

    if normalized_entities.isna().any():
        bad_rows = [
            index + 2
            for index, missing in enumerate(normalized_entities.isna())
            if missing
        ]
        raise DataValidationError(
            f"{source}: missing/blank {config.entity_id_column} identifier(s) "
            f"at data row(s): {bad_rows}"
        )

    duplicate_mask = normalized_entities.duplicated(keep=False)
    if duplicate_mask.any():
        duplicate_entities = sorted(set(normalized_entities[duplicate_mask]))
        raise DataValidationError(
            f"{source}: duplicate {config.entity_id_column} identifier(s): "
            + ", ".join(duplicate_entities)
        )

    validated[config.entity_id_column] = normalized_entities
    return validated


def _confirmed_decision_signature(
    row: pd.Series,
    *,
    config: ReviewPipelineConfig,
) -> tuple[str | None, str | None, str | None]:
    """Return a normalized comparison signature for one confirmed decision."""
    return (
        _canonical_spreadsheet_text(row[config.reviewed_business_id_column]),
        _canonical_spreadsheet_text(row[config.uncertainty_column]),
        _canonical_text(row[config.comment_column]),
    )


def validate_confirmed_entities_in_reference(
    confirmed_decisions: pd.DataFrame,
    reference_df: pd.DataFrame,
    *,
    config: ReviewPipelineConfig,
    source: str,
) -> None:
    """Require every confirmed entity to belong to a supplied reference frame."""
    entity_column = config.entity_id_column
    _raise_if_missing_columns(
        confirmed_decisions,
        [entity_column],
        source=source,
    )
    _raise_if_missing_columns(
        reference_df,
        [entity_column],
        source="reference frame",
    )

    confirmed_entities = {
        value
        for value in confirmed_decisions[entity_column].map(
            _canonical_spreadsheet_text
        )
        if value is not None
    }
    reference_entities = {
        value
        for value in reference_df[entity_column].map(
            _canonical_spreadsheet_text
        )
        if value is not None
    }

    outside = sorted(confirmed_entities - reference_entities)
    if outside:
        raise DataValidationError(
            f"{source}: additional {config.entity_name} decisions must belong to "
            f"the reference frame. Outside-frame examples: {outside[:20]}"
        )


def combine_confirmed_decision_sets(
    current_decisions: pd.DataFrame,
    additional_decisions: pd.DataFrame,
    *,
    config: ReviewPipelineConfig,
    additional_source: str = "additional confirmed decisions",
) -> AdditionalDecisionMergeResult:
    """Combine confirmed decisions, always keeping the current review on overlap."""
    current = validate_confirmed_decision_table(
        current_decisions,
        config=config,
        source="current confirmed decisions",
    )
    additional = validate_confirmed_decision_table(
        additional_decisions,
        config=config,
        source=additional_source,
    )

    entity_column = config.entity_id_column
    required = [
        entity_column,
        config.reviewed_business_id_column,
        config.uncertainty_column,
        config.comment_column,
    ]

    current_by_entity = current.set_index(entity_column, drop=False)
    identical_overlaps: list[str] = []
    conflicting_overlaps: list[str] = []
    additional_only_entities: list[str] = []
    additional_only_indices: list[object] = []

    for index, additional_row in additional.iterrows():
        entity = additional_row[entity_column]
        if entity not in current_by_entity.index:
            additional_only_entities.append(entity)
            additional_only_indices.append(index)
            continue

        current_row = current_by_entity.loc[entity]
        if _confirmed_decision_signature(
            current_row,
            config=config,
        ) == _confirmed_decision_signature(additional_row, config=config):
            identical_overlaps.append(entity)
        else:
            conflicting_overlaps.append(entity)

    additional_only = additional.loc[additional_only_indices, required]
    combined = pd.concat(
        [current.loc[:, required], additional_only],
        ignore_index=True,
        sort=False,
    )

    return AdditionalDecisionMergeResult(
        combined_decisions=combined,
        additional_decisions=additional,
        identical_overlaps=sorted(identical_overlaps),
        conflicting_overlaps=sorted(conflicting_overlaps),
        additional_only_entities=sorted(additional_only_entities),
    )

def export_dataframe_to_excel(
    df: pd.DataFrame,
    output_path: str | Path,
    *,
    sheet_name: str = "Sheet1",
) -> None:
    """Export a dataframe to Excel, preserving string-like values."""

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)

def export_dataframe_to_parquet(df: pd.DataFrame, output_path: str | Path) -> None:
    """Export a dataframe to parquet."""

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output, index=False)

def export_dataframe(
    df: pd.DataFrame,
    output_path: str | Path,
    *,
    sheet_name: str = "Sheet1",
) -> None:
    """Export a dataframe to parquet or Excel based on its extension."""

    output = Path(output_path)
    suffix = output.suffix.lower()
    if suffix in _VALID_EXCEL_SUFFIXES:
        export_dataframe_to_excel(df, output, sheet_name=sheet_name)
    elif suffix == ".parquet":
        export_dataframe_to_parquet(df, output)
    else:
        raise DataValidationError(
            f"Unsupported export format for {output.name!r}; expected Excel or parquet"
        )

def run_merge_pipeline(
    *,
    results_root: str | Path,
    config: ReviewPipelineConfig = EJ_SIREN_CONFIG,
    proposal_path: str | Path | None = None,
    plan_path: str | Path | None = None,
    correction_report_path: str | Path | None = None,
) -> dict[str, object]:
    """Run validation and consolidation for workflow step 04.

    ``proposal_path`` is optional, but recommended when a proposal table is
    available: sampled entities are then checked for membership and stratum
    consistency before outputs are built.
    """

    stratum_df, loaded_files = load_stratum_files(
        results_root,
        config=config,
        correction_report_path=correction_report_path,
    )
    proposal_df = (
        load_proposal_table(proposal_path, config=config) if proposal_path is not None else None
    )
    if proposal_df is not None:
        validate_stratum_entities_against_proposals(
            stratum_df,
            proposal_df,
            config=config,
            source=str(proposal_path),
        )

    plan_df = load_strata_plan(plan_path, config=config) if plan_path is not None else None
    missing_strata = report_missing_strata(
        plan_df=plan_df,
        stratum_df=stratum_df,
        config=config,
    )
    review_design = report_review_design_deviations(
        plan_df=plan_df,
        stratum_df=stratum_df,
        config=config,
    )

    reviewed_sample_df = filter_reviewed_cases(stratum_df, config=config)
    confirmed_decisions_df = build_confirmed_database(stratum_df, config=config)

    return {
        "loaded_files": loaded_files,
        "stratum_df": stratum_df,
        "proposal_df": proposal_df,
        "plan_df": plan_df,
        "reviewed_sample_df": reviewed_sample_df,
        "confirmed_decisions_df": confirmed_decisions_df,
        "missing_strata": missing_strata,
        **review_design,
    }

def main(argv: Sequence[str] | None = None) -> int:
    """Command-line interface for validating entity or establishment reviews."""

    import argparse

    parser = argparse.ArgumentParser(
        description="Validate configurable reviewer samples and export reviewed samples and confirmed decisions."
    )
    parser.add_argument(
        "--results-root", required=True, help="Directory containing per-stratum XLSX files"
    )
    parser.add_argument(
        "--proposal-path",
        help=(
            "Optional proposal table (Excel or parquet). Recommended: when supplied, "
            "sampled entities must exist there with the same stratum_id."
        ),
    )
    parser.add_argument(
        "--plan-path",
        help="Optional strata plan workbook, used to report planned strata with no review file.",
    )
    parser.add_argument(
        "--correction-report-out",
        help="CSV written with blocking workbook corrections; empty when validation passes.",
    )

    parser.add_argument("--entity-name", default="EJ", help="Public entity label, e.g. EJ or EGE")
    parser.add_argument(
        "--business-name", default="siren", help="Public business-id label, e.g. siren or siret"
    )
    parser.add_argument("--entity-id-column", default="EJ")
    parser.add_argument("--reviewed-business-id-column", default="Siren_retenu")
    parser.add_argument("--business-id-length", type=int, default=9)
    parser.add_argument("--stratum-id-column", default="stratum_id")
    parser.add_argument("--uncertainty-column", default="Incertitude1")
    parser.add_argument("--comment-column", default="Commentaire")
    parser.add_argument("--reviewer-column", default="reviewer")

    parser.add_argument(
        "--reviewed-sample-out",
        help="Optional reviewed-sample output (parquet or Excel)",
    )
    parser.add_argument(
        "--confirmed-decisions-out",
        help="Optional confirmed-decisions output (parquet or Excel)",
    )
    args = parser.parse_args(argv)

    config = ReviewPipelineConfig(
        entity_name=args.entity_name,
        business_name=args.business_name,
        entity_id_column=args.entity_id_column,
        reviewed_business_id_column=args.reviewed_business_id_column,
        business_id_length=args.business_id_length,
        stratum_id_column=args.stratum_id_column,
        uncertainty_column=args.uncertainty_column,
        comment_column=args.comment_column,
        reviewer_column=args.reviewer_column,
    )

    outputs = run_merge_pipeline(
        results_root=args.results_root,
        proposal_path=args.proposal_path,
        plan_path=args.plan_path,
        correction_report_path=args.correction_report_out,
        config=config,
    )

    if args.reviewed_sample_out:
        export_dataframe(outputs["reviewed_sample_df"], args.reviewed_sample_out)
    if args.confirmed_decisions_out:
        export_dataframe(outputs["confirmed_decisions_df"], args.confirmed_decisions_out)

    print("Review pipeline completed successfully.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
