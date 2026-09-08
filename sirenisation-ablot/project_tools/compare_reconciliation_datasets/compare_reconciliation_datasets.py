"""Compare two alternative EJ-SIREN or EGE-SIRET reconciliation datasets.

The tool is intentionally standalone: it does not depend on FINESS, SIRENE,
``project_config`` or any numbered workflow output.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Configuration to edit
# ---------------------------------------------------------------------------

MODE = "EJ-SIREN"  # "EJ-SIREN" or "EGE-SIRET"

DATASET1_PATH = Path("data/source/ANS/df_ans_ej_valides.parquet")
DATASET1_NAME = "ANS"
DATASET1_ENTITY_COLUMN = "nmfinessej_ej"
DATASET1_BUSINESS_COLUMN = "siren_ej_retenu"
DATASET1_SHEET_NAME: int | str = 0

DATASET2_PATH = Path("data/source/Adrien_Tortel/df_adrien_sirets_concordants_2026_06_sirenise.parquet")
DATASET2_NAME = "Adrien"
DATASET2_ENTITY_COLUMN = "nofinessej"
DATASET2_BUSINESS_COLUMN = "siren_prop"
DATASET2_SHEET_NAME: int | str = 0

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


@dataclass(frozen=True)
class ModeConfig:
    mode: str
    entity_column: str
    business_column: str
    entity_slug: str
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
        entity_slug="ej",
        business_slug="siren",
        entity_pad_width=9,
        business_pad_width=9,
    ),
    "EGE-SIRET": ModeConfig(
        mode="EGE-SIRET",
        entity_column="EGE",
        business_column="SIRET",
        entity_slug="ege",
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
class ComparisonConfig:
    mode: ModeConfig
    dataset1: DatasetConfig
    dataset2: DatasetConfig
    output_dir: Path


def configured_comparison() -> ComparisonConfig:
    """Build the comparison from the variables at the top of this file."""
    try:
        mode = MODES[MODE.upper()]
    except KeyError as exc:
        raise ValueError(f"MODE must be one of {sorted(MODES)}, not {MODE!r}.") from exc

    return ComparisonConfig(
        mode=mode,
        dataset1=DatasetConfig(
            DATASET1_PATH,
            DATASET1_NAME,
            DATASET1_ENTITY_COLUMN,
            DATASET1_BUSINESS_COLUMN,
            DATASET1_SHEET_NAME,
        ),
        dataset2=DatasetConfig(
            DATASET2_PATH,
            DATASET2_NAME,
            DATASET2_ENTITY_COLUMN,
            DATASET2_BUSINESS_COLUMN,
            DATASET2_SHEET_NAME,
        ),
        output_dir=OUTPUT_DIR,
    )


# ---------------------------------------------------------------------------
# Loading and validation
# ---------------------------------------------------------------------------


def _read_table(config: DatasetConfig) -> pd.DataFrame:
    path = config.path
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")

    columns = [config.entity_column, config.business_column]
    suffix = path.suffix.lower()

    if suffix == ".parquet":
        return pd.read_parquet(path, columns=columns)
    if suffix == ".xlsx":
        return pd.read_excel(
            path,
            sheet_name=config.sheet_name,
            usecols=columns,
            dtype="string",
        )
    if suffix == ".csv":
        return pd.read_csv(path, usecols=columns, dtype="string")

    raise ValueError(
        f"Unsupported input format for {path.name!r}: expected .parquet, .xlsx or .csv."
    )


def _normalize_identifier(value: Any, width: int) -> Any:
    if pd.isna(value):
        return pd.NA

    text = str(value).strip()
    if not text:
        return pd.NA
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if len(text) < width:
        text = text.zfill(width)
    return text


def _check_width(series: pd.Series, width: int, label: str) -> None:
    invalid = series[series.str.len().ne(width)]
    if invalid.empty:
        return
    examples = invalid.drop_duplicates().head(10).tolist()
    raise ValueError(
        f"{label} must contain identifiers of length {width} after normalization. "
        f"Invalid examples: {examples}"
    )


def load_dataset(config: DatasetConfig, mode: ModeConfig) -> pd.DataFrame:
    """Load one base and return its two normalized standard columns."""
    if not config.name.strip():
        raise ValueError("Dataset names must be non-empty.")
    if config.entity_column == config.business_column:
        raise ValueError(
            f"Dataset {config.name!r}: entity and business columns must be different."
        )

    frame = _read_table(config).copy()
    frame[config.entity_column] = frame[config.entity_column].map(
        lambda value: _normalize_identifier(value, mode.entity_pad_width)
    ).astype("string")
    frame[config.business_column] = frame[config.business_column].map(
        lambda value: _normalize_identifier(value, mode.business_pad_width)
    ).astype("string")

    if frame[config.entity_column].isna().any():
        raise ValueError(
            f"Dataset {config.name!r}: missing values in {config.entity_column!r}."
        )
    if frame[config.business_column].isna().any():
        raise ValueError(
            f"Dataset {config.name!r}: missing values in {config.business_column!r}."
        )

    _check_width(
        frame[config.entity_column],
        mode.entity_pad_width,
        f"Dataset {config.name!r} / {config.entity_column!r}",
    )
    _check_width(
        frame[config.business_column],
        mode.business_pad_width,
        f"Dataset {config.name!r} / {config.business_column!r}",
    )

    duplicate_pairs = frame.duplicated(
        [config.entity_column, config.business_column], keep=False
    )
    if duplicate_pairs.any():
        examples = (
            frame.loc[
                duplicate_pairs,
                [config.entity_column, config.business_column],
            ]
            .drop_duplicates()
            .head(10)
            .to_dict("records")
        )
        raise ValueError(
            f"Dataset {config.name!r}: duplicate entity-business pairs after "
            f"normalization. Examples: {examples}"
        )

    return frame.rename(
        columns={
            config.entity_column: mode.entity_column,
            config.business_column: mode.business_column,
        }
    )[[mode.entity_column, mode.business_column]]


# ---------------------------------------------------------------------------
# Comparison and statistics
# ---------------------------------------------------------------------------


def _proposals_by_entity(
    frame: pd.DataFrame, mode: ModeConfig
) -> dict[str, tuple[str, ...]]:
    grouped = frame.groupby(mode.entity_column, sort=False)[mode.business_column]
    return {
        str(entity): tuple(sorted(series.astype(str).unique().tolist()))
        for entity, series in grouped
    }


def _consistency_type(
    proposals1: tuple[str, ...], proposals2: tuple[str, ...]
) -> str:
    set1, set2 = set(proposals1), set(proposals2)
    if set1 == set2:
        return "Total consistency"
    if set1.intersection(set2):
        return "Partial consistency"
    return "Total inconsistency"


def build_consistency_table(
    dataset1: pd.DataFrame,
    dataset2: pd.DataFrame,
    config: ComparisonConfig,
) -> pd.DataFrame:
    """Return one row per entity in the union of both datasets."""
    p1 = _proposals_by_entity(dataset1, config.mode)
    p2 = _proposals_by_entity(dataset2, config.mode)
    entities1, entities2 = set(p1), set(p2)

    rows: list[dict[str, object]] = []
    for entity in sorted(entities1 | entities2):
        proposals1 = p1.get(entity, ())
        proposals2 = p2.get(entity, ())
        in1, in2 = entity in entities1, entity in entities2

        if in1 and in2:
            source = f"{config.dataset1.name} + {config.dataset2.name}"
            consistency = _consistency_type(proposals1, proposals2)
        elif in1:
            source = config.dataset1.name
            consistency = pd.NA
        else:
            source = config.dataset2.name
            consistency = pd.NA

        rows.append(
            {
                config.mode.entity_column: entity,
                "source_dataset": source,
                "dataset1__proposals": proposals1,
                "dataset1__proposal_count": len(proposals1),
                "dataset2__proposals": proposals2,
                "dataset2__proposal_count": len(proposals2),
                "consistency_type": consistency,
            }
        )

    return pd.DataFrame(
        rows,
        columns=[
            config.mode.entity_column,
            "source_dataset",
            "dataset1__proposals",
            "dataset1__proposal_count",
            "dataset2__proposals",
            "dataset2__proposal_count",
            "consistency_type",
        ],
    )


def _summary_for_both(frame: pd.DataFrame) -> dict[str, float | int]:
    if frame.empty:
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
        "total_consistency_n": int(frame["consistency_type"].eq("Total consistency").sum()),
        "total_consistency_rate": float(frame["consistency_type"].eq("Total consistency").mean()),
        "partial_consistency_n": int(frame["consistency_type"].eq("Partial consistency").sum()),
        "partial_consistency_rate": float(frame["consistency_type"].eq("Partial consistency").mean()),
        "total_inconsistency_n": int(frame["consistency_type"].eq("Total inconsistency").sum()),
        "total_inconsistency_rate": float(frame["consistency_type"].eq("Total inconsistency").mean()),
        "avg_dataset1_proposals": float(frame["dataset1__proposal_count"].mean()),
        "avg_dataset2_proposals": float(frame["dataset2__proposal_count"].mean()),
    }


def compute_main_statistics(
    consistency: pd.DataFrame, config: ComparisonConfig
) -> dict[str, object]:
    source = consistency["source_dataset"]
    source1 = config.dataset1.name
    source2 = config.dataset2.name
    source_both = f"{source1} + {source2}"

    n_only1 = int(source.eq(source1).sum())
    n_only2 = int(source.eq(source2).sum())
    n_both = int(source.eq(source_both).sum())
    n_union = len(consistency)
    slug = config.mode.entity_slug

    return {
        "general": {
            "mode": config.mode.mode,
            "dataset1_name": source1,
            "dataset2_name": source2,
            f"n_{slug}_dataset1": n_only1 + n_both,
            f"n_{slug}_dataset2": n_only2 + n_both,
            f"n_{slug}_union": n_union,
            f"n_{slug}_in_both_datasets": n_both,
            f"n_{slug}_only_dataset1": n_only1,
            f"n_{slug}_only_dataset2": n_only2,
            f"pct_{slug}_in_both_over_union": float(n_both / n_union) if n_union else 0.0,
        },
        "entities_in_both_datasets": _summary_for_both(
            consistency.loc[source.eq(source_both)]
        ),
    }


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def _excel_ready(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for column in ("dataset1__proposals", "dataset2__proposals"):
        out[column] = out[column].map(
            lambda values: " | ".join(values) if isinstance(values, tuple) else ""
        )
    return out


def export_results(
    consistency: pd.DataFrame,
    statistics: dict[str, object],
    config: ComparisonConfig,
) -> dict[str, Path]:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    prefix = config.mode.output_prefix

    parquet_path = config.output_dir / f"{prefix}_consistency.parquet"
    excel_path = config.output_dir / f"{prefix}_consistency.xlsx"
    json_path = config.output_dir / f"{prefix}_main_statistics.json"

    consistency.to_parquet(parquet_path, index=False)
    _excel_ready(consistency).to_excel(
        excel_path,
        sheet_name="consistency",
        index=False,
        engine="openpyxl",
    )
    with json_path.open("w", encoding="utf-8") as file:
        json.dump(statistics, file, ensure_ascii=False, indent=2)

    return {
        "consistency_parquet": parquet_path,
        "consistency_excel": excel_path,
        "main_statistics": json_path,
    }


def run(
    config: ComparisonConfig | None = None,
    *,
    write_outputs: bool = True,
) -> dict[str, object]:
    config = config or configured_comparison()
    if config.dataset1.name == config.dataset2.name:
        raise ValueError("Dataset names must be different.")

    dataset1 = load_dataset(config.dataset1, config.mode)
    dataset2 = load_dataset(config.dataset2, config.mode)
    consistency = build_consistency_table(dataset1, dataset2, config)
    statistics = compute_main_statistics(consistency, config)
    output_paths = (
        export_results(consistency, statistics, config) if write_outputs else {}
    )

    return {
        "dataset1": dataset1,
        "dataset2": dataset2,
        "consistency": consistency,
        "main_statistics": statistics,
        "output_paths": output_paths,
    }


def main() -> None:
    config = configured_comparison()
    result = run(config)
    general = result["main_statistics"]["general"]
    slug = config.mode.entity_slug

    print(f"{config.mode.mode} pairwise comparison")
    print(f"- {config.dataset1.name}: {general[f'n_{slug}_dataset1']:,}")
    print(f"- {config.dataset2.name}: {general[f'n_{slug}_dataset2']:,}")
    print(f"- union: {general[f'n_{slug}_union']:,}")
    print(f"- present in both: {general[f'n_{slug}_in_both_datasets']:,}")
    print("- saved:")
    for path in result["output_paths"].values():
        print(f"  - {path}")


if __name__ == "__main__":
    main()
