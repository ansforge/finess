"""Evaluate one external reconciliation dataset against a weighted review sample."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Configuration to edit
# ---------------------------------------------------------------------------

MODE = "EGE-SIRET"  # "EJ-SIREN" or "EGE-SIRET"

DATASET_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "source"
    / "Adrien_Tortel"
    / "df_adrien_sirets_concordants_2026_06_clean.parquet"
)
DATASET_NAME = "Adrien original"
DATASET_ENTITY_COLUMN = "nofinesset"
DATASET_BUSINESS_COLUMN = "siret_prop"
DATASET_SHEET_NAME: int | str = 0

REVIEW_SAMPLE_PATH = Path(__file__).resolve().parent / "output/ege_review_sample.parquet"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"


@dataclass(frozen=True)
class ModeConfig:
    mode: str
    entity_column: str
    business_column: str
    retained_business_column: str
    entity_slug: str
    entity_plural: str
    business_slug: str
    entity_pad_width: int
    business_pad_width: int

    @property
    def output_prefix(self) -> str:
        return f"{self.entity_slug}_{self.business_slug}"


MODES = {
    "EJ-SIREN": ModeConfig(
        mode="EJ-SIREN",
        entity_column="EJ",
        business_column="SIREN",
        retained_business_column="Siren_retenu",
        entity_slug="ej",
        entity_plural="EJs",
        business_slug="siren",
        entity_pad_width=9,
        business_pad_width=9,
    ),
    "EGE-SIRET": ModeConfig(
        mode="EGE-SIRET",
        entity_column="EGE",
        business_column="SIRET",
        retained_business_column="Siret_retenu",
        entity_slug="ege",
        entity_plural="EGEs",
        business_slug="siret",
        entity_pad_width=9,
        business_pad_width=14,
    ),
}


@dataclass(frozen=True)
class DatasetConfig:
    path: Path
    name: str
    entity_column: str
    business_column: str
    sheet_name: int | str = 0


@dataclass(frozen=True)
class EvaluationConfig:
    mode: ModeConfig
    dataset: DatasetConfig
    review_sample_path: Path
    output_dir: Path


def configured_evaluation() -> EvaluationConfig:
    try:
        mode = MODES[MODE.upper()]
    except KeyError as exc:
        raise ValueError(f"MODE must be one of {sorted(MODES)}, not {MODE!r}.") from exc

    if not DATASET_NAME.strip():
        raise ValueError("DATASET_NAME must be non-empty.")

    return EvaluationConfig(
        mode=mode,
        dataset=DatasetConfig(
            path=DATASET_PATH,
            name=DATASET_NAME,
            entity_column=DATASET_ENTITY_COLUMN,
            business_column=DATASET_BUSINESS_COLUMN,
            sheet_name=DATASET_SHEET_NAME,
        ),
        review_sample_path=REVIEW_SAMPLE_PATH,
        output_dir=OUTPUT_DIR,
    )


def _canonical_text(value: Any) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text or None


def _normalize_identifier(value: Any, width: int, *, allow_missing: bool = False) -> Any:
    text = _canonical_text(value)
    if text is None or text.upper() in {"NA", "N/A"}:
        if allow_missing:
            return pd.NA
        return pd.NA
    if len(text) < width:
        text = text.zfill(width)
    return text


def _check_width(series: pd.Series, width: int, label: str) -> None:
    nonmissing = series.dropna().astype("string")
    invalid = nonmissing.loc[nonmissing.str.len().ne(width)]
    if invalid.empty:
        return
    examples = invalid.drop_duplicates().head(10).tolist()
    raise ValueError(
        f"{label} must contain identifiers of length {width} after normalization. "
        f"Invalid examples: {examples}"
    )


def _read_dataset(config: DatasetConfig) -> pd.DataFrame:
    if not config.path.is_file():
        raise FileNotFoundError(f"Input dataset not found: {config.path}")
    columns = [config.entity_column, config.business_column]
    suffix = config.path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(config.path, columns=columns)
    if suffix == ".xlsx":
        return pd.read_excel(
            config.path,
            sheet_name=config.sheet_name,
            usecols=columns,
            dtype="string",
        )
    if suffix == ".csv":
        return pd.read_csv(config.path, usecols=columns, dtype="string")
    raise ValueError(
        f"Unsupported dataset format for {config.path.name!r}: expected .parquet, .xlsx or .csv."
    )


def load_dataset(config: DatasetConfig, mode: ModeConfig) -> pd.DataFrame:
    if config.entity_column == config.business_column:
        raise ValueError("Dataset entity and business columns must be different.")

    frame = _read_dataset(config).copy()
    frame[config.entity_column] = frame[config.entity_column].map(
        lambda value: _normalize_identifier(value, mode.entity_pad_width)
    ).astype("string")
    frame[config.business_column] = frame[config.business_column].map(
        lambda value: _normalize_identifier(value, mode.business_pad_width)
    ).astype("string")

    if frame[config.entity_column].isna().any():
        raise ValueError(f"Dataset contains missing {config.entity_column!r} values.")
    if frame[config.business_column].isna().any():
        raise ValueError(f"Dataset contains missing {config.business_column!r} values.")

    _check_width(frame[config.entity_column], mode.entity_pad_width, config.entity_column)
    _check_width(frame[config.business_column], mode.business_pad_width, config.business_column)

    duplicate = frame.duplicated([config.entity_column, config.business_column], keep=False)
    if duplicate.any():
        examples = (
            frame.loc[duplicate, [config.entity_column, config.business_column]]
            .drop_duplicates()
            .head(10)
            .to_dict("records")
        )
        raise ValueError(
            f"Dataset contains duplicate {mode.mode} pairs after normalization. "
            f"Examples: {examples}"
        )

    return frame.rename(
        columns={
            config.entity_column: mode.entity_column,
            config.business_column: mode.business_column,
        }
    )[[mode.entity_column, mode.business_column]]


def load_review_sample(path: Path, mode: ModeConfig) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Review sample not found: {path}")
    if path.suffix.lower() != ".parquet":
        raise ValueError("The review sample must be the Parquet produced by build_review_sample.py.")

    sample = pd.read_parquet(path).copy()
    required = [
        mode.entity_column,
        mode.retained_business_column,
        "Incertitude1",
        "stratum_id",
        "sampling_weight",
        "calibrated_weight",
        "to_close",
    ]
    missing = [column for column in required if column not in sample.columns]
    if missing:
        raise KeyError(f"Review sample is missing columns: {missing}")

    sample = sample[required].copy()
    sample[mode.entity_column] = sample[mode.entity_column].map(
        lambda value: _normalize_identifier(value, mode.entity_pad_width)
    ).astype("string")
    sample[mode.retained_business_column] = sample[mode.retained_business_column].map(
        lambda value: _normalize_identifier(
            value,
            mode.business_pad_width,
            allow_missing=True,
        )
    ).astype("string")

    if sample[mode.entity_column].isna().any():
        raise ValueError(f"Review sample contains missing {mode.entity_column} identifiers.")
    _check_width(sample[mode.entity_column], mode.entity_pad_width, mode.entity_column)
    _check_width(
        sample[mode.retained_business_column],
        mode.business_pad_width,
        mode.retained_business_column,
    )
    if sample[mode.entity_column].duplicated().any():
        raise ValueError(f"Review sample must contain exactly one row per {mode.entity_column}.")

    for column in ["sampling_weight", "calibrated_weight"]:
        values = pd.to_numeric(sample[column], errors="coerce")
        if values.isna().any() or (values <= 0).any():
            raise ValueError(f"Review sample column {column!r} must be positive and numeric.")
        sample[column] = values.astype(float)

    close_values = sample["to_close"]
    if str(close_values.dtype) != "boolean":
        normalized = close_values.astype("string").str.strip().str.lower()
        mapping = {"true": True, "false": False, "1": True, "0": False}
        parsed = normalized.map(mapping)
        if parsed.isna().any():
            raise ValueError("Review sample column 'to_close' must be boolean.")
        sample["to_close"] = parsed.astype("boolean")

    return sample


def _proposals_by_entity(frame: pd.DataFrame, mode: ModeConfig) -> dict[str, tuple[str, ...]]:
    grouped = frame.groupby(mode.entity_column, sort=False)[mode.business_column]
    return {
        str(entity): tuple(sorted(series.astype(str).unique().tolist()))
        for entity, series in grouped
    }


def build_review_comparison(
    dataset: pd.DataFrame,
    sample: pd.DataFrame,
    *,
    mode: ModeConfig,
) -> pd.DataFrame:
    proposals = _proposals_by_entity(dataset, mode)
    rows: list[dict[str, object]] = []

    for row in sample.itertuples(index=False, name=None):
        values = dict(zip(sample.columns, row))
        entity = str(values[mode.entity_column])
        human_business = values[mode.retained_business_column]
        entity_proposals = proposals.get(entity, ())
        covered = bool(entity_proposals)
        to_close = bool(values["to_close"])

        if to_close or not covered:
            correct: object = pd.NA
        elif pd.isna(human_business):
            correct = False
        else:
            correct = str(human_business) in set(entity_proposals)

        rows.append(
            {
                mode.entity_column: entity,
                mode.retained_business_column: human_business,
                "dataset_proposals": entity_proposals,
                "proposal_count": len(entity_proposals),
                "covered": covered,
                "correct": correct,
                "to_close": to_close,
                "stratum_id": values["stratum_id"],
                "sampling_weight": float(values["sampling_weight"]),
                "calibrated_weight": float(values["calibrated_weight"]),
            }
        )

    result = pd.DataFrame(rows)
    result["covered"] = result["covered"].astype("boolean")
    result["correct"] = result["correct"].astype("boolean")
    result["to_close"] = result["to_close"].astype("boolean")
    return result


def _proportion(numerator: float, denominator: float) -> float | object:
    if denominator <= 0:
        return pd.NA
    return numerator / denominator


def build_performance_summary(
    comparison: pd.DataFrame, *, mode: ModeConfig
) -> pd.DataFrame:
    reviewed_n = len(comparison)
    to_close_mask = comparison["to_close"].fillna(False).astype(bool)
    to_match_mask = ~to_close_mask
    covered_mask = to_match_mask & comparison["covered"].fillna(False).astype(bool)
    correct_mask = covered_mask & comparison["correct"].fillna(False).astype(bool)

    to_match_n = int(to_match_mask.sum())
    to_close_n = int(to_close_mask.sum())
    covered_n = int(covered_mask.sum())
    correct_n = int(correct_mask.sum())

    calibrated = comparison["calibrated_weight"].astype(float)
    calibrated_to_match = float(calibrated.loc[to_match_mask].sum())
    calibrated_covered = float(calibrated.loc[covered_mask].sum())
    calibrated_correct = float(calibrated.loc[correct_mask].sum())

    rows = [
        {
            "Metric": f"{mode.entity_plural} in review sample",
            "Population count": reviewed_n,
            "Proportion": 1.0 if reviewed_n else pd.NA,
            "Denominator": "Review sample",
            "Denominator population": reviewed_n,
        },
        {
            "Metric": f"{mode.entity_plural} to match",
            "Population count": to_match_n,
            "Proportion": _proportion(to_match_n, reviewed_n),
            "Denominator": "Review sample",
            "Denominator population": reviewed_n,
        },
        {
            "Metric": f"{mode.entity_plural} to close",
            "Population count": to_close_n,
            "Proportion": _proportion(to_close_n, reviewed_n),
            "Denominator": "Review sample",
            "Denominator population": reviewed_n,
        },
        {
            "Metric": "Coverage — raw",
            "Population count": covered_n,
            "Proportion": _proportion(covered_n, to_match_n),
            "Denominator": f"{mode.entity_plural} to match",
            "Denominator population": to_match_n,
        },
        {
            "Metric": "Coverage — calibrated",
            "Population count": round(calibrated_covered, 2),
            "Proportion": _proportion(calibrated_covered, calibrated_to_match),
            "Denominator": f"Estimated {mode.entity_plural} to match",
            "Denominator population": round(calibrated_to_match, 2),
        },
        {
            "Metric": "Correct when proposed — raw",
            "Population count": correct_n,
            "Proportion": _proportion(correct_n, covered_n),
            "Denominator": f"Covered {mode.entity_plural} to match",
            "Denominator population": covered_n,
        },
        {
            "Metric": "Correct when proposed — calibrated",
            "Population count": round(calibrated_correct, 2),
            "Proportion": _proportion(calibrated_correct, calibrated_covered),
            "Denominator": f"Estimated covered {mode.entity_plural} to match",
            "Denominator population": round(calibrated_covered, 2),
        },
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "Metric",
            "Population count",
            "Proportion",
            "Denominator",
            "Denominator population",
        ],
    )


def _safe_slug(text: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z]+", "_", text.strip()).strip("_").lower()
    return slug or "dataset"


def export_summary(summary: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        summary.to_excel(writer, index=False, sheet_name="performance_summary")
        worksheet = writer.sheets["performance_summary"]
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions
        widths = {
            "A": 38,
            "B": 20,
            "C": 18,
            "D": 36,
            "E": 24,
        }
        for column, width in widths.items():
            worksheet.column_dimensions[column].width = width

        for cell in worksheet["C"][1:]:
            cell.number_format = "0.00%"


def run(config: EvaluationConfig | None = None) -> dict[str, object]:
    config = config or configured_evaluation()
    dataset = load_dataset(config.dataset, config.mode)
    sample = load_review_sample(config.review_sample_path, config.mode)
    comparison = build_review_comparison(dataset, sample, mode=config.mode)
    summary = build_performance_summary(comparison, mode=config.mode)

    config.output_dir.mkdir(parents=True, exist_ok=True)
    slug = _safe_slug(config.dataset.name)
    prefix = f"{slug}_{config.mode.output_prefix}"
    comparison_path = config.output_dir / f"{prefix}_review_comparison.parquet"
    summary_path = config.output_dir / f"{prefix}_performance_summary.xlsx"

    comparison.to_parquet(comparison_path, index=False)
    export_summary(summary, summary_path)

    print(f"{config.dataset.name} / {config.mode.mode}")
    print(
        f"- dataset {config.mode.entity_plural}: "
        f"{dataset[config.mode.entity_column].nunique():,}"
    )
    print(f"- review sample: {len(sample):,}")
    print(f"- saved: {comparison_path}")
    print(f"- saved: {summary_path}")

    return {
        "dataset": dataset,
        "review_sample": sample,
        "comparison": comparison,
        "summary": summary,
        "output_paths": [comparison_path, summary_path],
    }


def main() -> None:
    run()


if __name__ == "__main__":
    main()
