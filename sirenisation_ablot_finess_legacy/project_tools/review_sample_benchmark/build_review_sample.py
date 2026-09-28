"""Publish the reviewed EJ/EGE samples with Stage 05 sampling weights.

This project tool is specific to the current study. It takes the confirmed manual
review decisions, attaches their stratum and the Stage 05 design/calibrated weights,
and writes compact Parquet and Excel files that can be shared independently of the rest
of the workflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from project_config import PATHS

OUTPUT_DIR = Path(__file__).resolve().parent / "output"

VALID_UNCERTAINTY_VALUES = frozenset({"-12", "-2", "-1", "0", "1", "2", "12"})


@dataclass(frozen=True)
class SampleMode:
    name: str
    entity_column: str
    retained_business_column: str
    entity_pad_width: int
    business_pad_width: int
    decisions_path: Path
    mapping_path: Path
    mapping_stratum_column: str
    analysis_path: Path
    reviewed_count_column: str
    output_name: str


MODES = (
    SampleMode(
        name="EJ-SIREN",
        entity_column="EJ",
        retained_business_column="Siren_retenu",
        entity_pad_width=9,
        business_pad_width=9,
        decisions_path=PATHS.stage04_ej_all_confirmed,
        mapping_path=PATHS.stage02_ej_stratified_proposals,
        mapping_stratum_column="stratum_id",
        analysis_path=PATHS.stage05_ej_strata_analysis,
        reviewed_count_column="EJs examined",
        output_name="ej_review_sample.parquet",
    ),
    SampleMode(
        name="EGE-SIRET",
        entity_column="EGE",
        retained_business_column="Siret_retenu",
        entity_pad_width=9,
        business_pad_width=14,
        decisions_path=PATHS.stage04_ege_confirmed,
        mapping_path=PATHS.stage02_ege_pooled_proposals,
        mapping_stratum_column="stratum_id",
        analysis_path=PATHS.stage05_ege_strata_analysis,
        reviewed_count_column="EGEs examined",
        output_name="ege_review_sample.parquet",
    ),
)


def _canonical_text(value: Any) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text or None


def _normalize_identifier(value: Any, width: int, *, allow_special: bool = False) -> Any:
    text = _canonical_text(value)
    if text is None:
        return pd.NA
    if allow_special and text.upper() in {"NA", "N/A"}:
        return pd.NA
    if len(text) < width:
        text = text.zfill(width)
    return text


def _validate_width(series: pd.Series, width: int, label: str) -> None:
    nonmissing = series.dropna().astype("string")
    invalid = nonmissing.loc[nonmissing.str.len().ne(width)]
    if invalid.empty:
        return
    examples = invalid.drop_duplicates().head(10).tolist()
    raise ValueError(
        f"{label} must contain identifiers of length {width} after normalization. "
        f"Invalid examples: {examples}"
    )


def _validate_decisions(decisions: pd.DataFrame, mode: SampleMode) -> pd.DataFrame:
    required = [mode.entity_column, mode.retained_business_column, "Incertitude1"]
    missing = [column for column in required if column not in decisions.columns]
    if missing:
        raise KeyError(f"{mode.decisions_path}: missing columns {missing}")

    out = decisions[required].copy()
    out[mode.entity_column] = out[mode.entity_column].map(
        lambda value: _normalize_identifier(value, mode.entity_pad_width)
    ).astype("string")
    if out[mode.entity_column].isna().any():
        raise ValueError(f"{mode.name}: manual decisions contain missing entity identifiers.")
    _validate_width(out[mode.entity_column], mode.entity_pad_width, mode.entity_column)

    duplicate = out[mode.entity_column].duplicated(keep=False)
    if duplicate.any():
        examples = out.loc[duplicate, mode.entity_column].drop_duplicates().head(10).tolist()
        raise ValueError(
            f"{mode.name}: manual decisions must contain one row per entity. "
            f"Duplicates: {examples}"
        )

    out[mode.retained_business_column] = out[mode.retained_business_column].map(
        lambda value: _normalize_identifier(
            value,
            mode.business_pad_width,
            allow_special=True,
        )
    ).astype("string")
    _validate_width(
        out[mode.retained_business_column],
        mode.business_pad_width,
        mode.retained_business_column,
    )

    uncertainty = out["Incertitude1"].map(_canonical_text)
    invalid_uncertainty = uncertainty.notna() & ~uncertainty.isin(VALID_UNCERTAINTY_VALUES)
    if invalid_uncertainty.any():
        examples = uncertainty.loc[invalid_uncertainty].drop_duplicates().head(10).tolist()
        raise ValueError(
            f"{mode.name}: invalid Incertitude1 values. Examples: {examples}; "
            f"allowed values are {sorted(VALID_UNCERTAINTY_VALUES)}."
        )
    # Confirmed review data normally carry an explicit code, but an empty value is
    # semantically equivalent to 0 in the review consolidation logic.
    uncertainty = uncertainty.fillna("0")
    out["Incertitude1"] = uncertainty.astype("string")
    out["to_close"] = uncertainty.map(lambda value: int(value) < 0).astype("boolean")
    return out


def _entity_stratum_mapping(mapping: pd.DataFrame, mode: SampleMode) -> pd.DataFrame:
    required = [mode.entity_column, mode.mapping_stratum_column]
    missing = [column for column in required if column not in mapping.columns]
    if missing:
        raise KeyError(f"{mode.mapping_path}: missing columns {missing}")

    out = mapping[required].copy()
    out[mode.entity_column] = out[mode.entity_column].map(
        lambda value: _normalize_identifier(value, mode.entity_pad_width)
    ).astype("string")
    out["stratum_id"] = out[mode.mapping_stratum_column].map(_canonical_text).astype("string")

    if out[mode.entity_column].isna().any() or out["stratum_id"].isna().any():
        raise ValueError(f"{mode.name}: entity-to-stratum mapping contains missing values.")

    pairs = out[[mode.entity_column, "stratum_id"]].drop_duplicates()
    ambiguous = pairs[mode.entity_column].duplicated(keep=False)
    if ambiguous.any():
        examples = pairs.loc[ambiguous, mode.entity_column].drop_duplicates().head(10).tolist()
        raise ValueError(
            f"{mode.name}: entities must map to exactly one stratum. Examples: {examples}"
        )
    return pairs.reset_index(drop=True)


def _stratum_weights(analysis: pd.DataFrame, mode: SampleMode) -> pd.DataFrame:
    required = [
        "Stratum ID",
        "Population size",
        mode.reviewed_count_column,
        "Sampling weight",
    ]
    missing = [column for column in required if column not in analysis.columns]
    if missing:
        raise KeyError(f"{mode.analysis_path}: missing Stage 05 columns {missing}")

    out = analysis[required].copy()
    out["stratum_id"] = out["Stratum ID"].map(_canonical_text).astype("string")
    if out["stratum_id"].isna().any():
        raise ValueError(f"{mode.name}: Stage 05 analysis contains missing stratum IDs.")
    if out["stratum_id"].duplicated().any():
        raise ValueError(f"{mode.name}: Stage 05 analysis must contain one row per stratum.")

    population = pd.to_numeric(out["Population size"], errors="coerce")
    reviewed = pd.to_numeric(out[mode.reviewed_count_column], errors="coerce")
    sampling_weight = pd.to_numeric(out["Sampling weight"], errors="coerce")

    if population.isna().any() or (population < 0).any():
        raise ValueError(f"{mode.name}: invalid Stage 05 population sizes.")
    if reviewed.isna().any() or (reviewed <= 0).any():
        raise ValueError(f"{mode.name}: every exported review stratum must have reviewed entities.")
    if sampling_weight.isna().any() or (sampling_weight <= 0).any():
        raise ValueError(f"{mode.name}: Stage 05 sampling weights must be positive.")

    design_expansion = reviewed * sampling_weight
    calibration = population / design_expansion
    calibrated_weight = sampling_weight * calibration

    result = pd.DataFrame(
        {
            "stratum_id": out["stratum_id"],
            "sampling_weight": sampling_weight.astype(float),
            "calibrated_weight": calibrated_weight.astype(float),
            "_population_size": population.astype(float),
            "_reviewed_count": reviewed.astype(float),
        }
    )
    return result


def build_shareable_sample(
    decisions: pd.DataFrame,
    mapping: pd.DataFrame,
    analysis: pd.DataFrame,
    *,
    mode: SampleMode,
) -> pd.DataFrame:
    """Return one weighted, shareable manual-decision row per reviewed entity."""
    decisions_clean = _validate_decisions(decisions, mode)
    mapping_clean = _entity_stratum_mapping(mapping, mode)
    weights = _stratum_weights(analysis, mode)

    sample = decisions_clean.merge(
        mapping_clean,
        on=mode.entity_column,
        how="left",
        validate="1:1",
    )
    if sample["stratum_id"].isna().any():
        examples = sample.loc[sample["stratum_id"].isna(), mode.entity_column].head(10).tolist()
        raise ValueError(
            f"{mode.name}: reviewed entities are missing from the sampling-frame mapping. "
            f"Examples: {examples}"
        )

    sample = sample.merge(
        weights[["stratum_id", "sampling_weight", "calibrated_weight"]],
        on="stratum_id",
        how="left",
        validate="many_to_one",
    )
    if sample[["sampling_weight", "calibrated_weight"]].isna().any().any():
        missing_strata = sample.loc[
            sample["calibrated_weight"].isna(), "stratum_id"
        ].drop_duplicates().tolist()
        raise ValueError(
            f"{mode.name}: missing Stage 05 weights for reviewed strata: {missing_strata[:10]}"
        )

    # The calibrated weight is defined so reviewed weights sum to the exact stratum
    # population. Verify that the published sample preserves that identity.
    by_stratum = sample.groupby("stratum_id", sort=False)["calibrated_weight"].sum()
    population_by_stratum = weights.set_index("stratum_id")["_population_size"]
    expected = population_by_stratum.reindex(by_stratum.index)
    mismatch = (by_stratum - expected).abs().gt(0.02)
    if mismatch.any():
        bad = by_stratum.index[mismatch].tolist()
        raise ValueError(
            f"{mode.name}: calibrated review weights do not reproduce the Stage 05 "
            f"population in strata {bad[:10]}."
        )

    columns = [
        mode.entity_column,
        mode.retained_business_column,
        "Incertitude1",
        "stratum_id",
        "sampling_weight",
        "calibrated_weight",
        "to_close",
    ]
    return sample[columns].sort_values(mode.entity_column).reset_index(drop=True)


def _load_analysis(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Stage 05 analysis not found: {path}")
    return pd.read_excel(path, sheet_name="analysis", dtype="string")


def build_mode(mode: SampleMode, output_dir: Path = OUTPUT_DIR) -> list[Path]:
    for path in (mode.decisions_path, mode.mapping_path, mode.analysis_path):
        if not path.is_file():
            raise FileNotFoundError(f"Required project artifact not found: {path}")

    decisions = pd.read_parquet(mode.decisions_path)
    mapping = pd.read_parquet(
        mode.mapping_path,
        columns=[mode.entity_column, mode.mapping_stratum_column],
    )
    analysis = _load_analysis(mode.analysis_path)

    sample = build_shareable_sample(decisions, mapping, analysis, mode=mode)
    output_dir.mkdir(parents=True, exist_ok=True)

    parquet_output = output_dir / mode.output_name
    excel_output = parquet_output.with_suffix(".xlsx")
    sample.to_parquet(parquet_output, index=False)
    sample.to_excel(excel_output, index=False)

    print(f"{mode.name} review sample")
    print(f"- reviewed entities: {len(sample):,}")
    print(f"- to match: {(~sample['to_close']).sum():,}")
    print(f"- to close: {sample['to_close'].sum():,}")
    print("- saved:")
    print(f"  - {parquet_output}")
    print(f"  - {excel_output}")
    return [parquet_output, excel_output]


def main() -> None:
    outputs: list[Path] = []
    for mode in MODES:
        outputs.extend(build_mode(mode))

    print("Published review samples:")
    for path in outputs:
        print(f"- {path}")


if __name__ == "__main__":
    main()
