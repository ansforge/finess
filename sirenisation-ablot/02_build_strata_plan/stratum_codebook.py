"""Load, validate and export Stage 02 stratum codebooks.

The stratification engine creates the codebook together with entity assignments
and the strata plan. This module deliberately contains no stratification
definition: it only enforces the generic workbook contract.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

MISSING_LEVEL = "<NA>"


def validate_stratum_codebook(codebook: pd.DataFrame) -> pd.DataFrame:
    """Validate the generic one-row-per-stratum codebook contract."""
    if "stratum_id" not in codebook.columns:
        raise KeyError("Stratum codebook must contain 'stratum_id'.")
    if codebook.columns.duplicated().any():
        duplicates = codebook.columns[codebook.columns.duplicated()].tolist()
        raise ValueError(f"Stratum codebook contains duplicate columns: {duplicates}")

    normalized = codebook.copy()
    normalized["stratum_id"] = (
        normalized["stratum_id"].astype("string").str.strip().replace("", pd.NA)
    )
    if normalized["stratum_id"].isna().any():
        raise ValueError("Stratum codebook contains missing stratum_id values.")

    for column in normalized.columns:
        if column == "stratum_id":
            continue
        normalized[column] = (
            normalized[column]
            .astype("string")
            .fillna(MISSING_LEVEL)
            .str.strip()
            .replace("", MISSING_LEVEL)
        )

    duplicate_ids = normalized["stratum_id"].duplicated(keep=False)
    if duplicate_ids.any():
        sample = normalized.loc[duplicate_ids].head(20).to_dict("records")
        raise ValueError(
            "Stratum codebook must contain exactly one row per stratum_id. "
            f"Duplicate rows: {sample}"
        )

    return normalized.sort_values("stratum_id", kind="stable").reset_index(drop=True)


def load_stratum_codebook(path: str | Path) -> pd.DataFrame:
    """Load and validate the generated Stage 02 codebook workbook."""
    codebook = pd.read_excel(
        Path(path),
        sheet_name="stratum_codebook",
        dtype="string",
        keep_default_na=False,
    )
    return validate_stratum_codebook(codebook)


def export_stratum_codebook(
    path: str | Path,
    codebook: pd.DataFrame,
) -> Path:
    """Validate and write the generated Stage 02 codebook workbook."""
    from openpyxl.styles import Alignment, Font
    from openpyxl.utils import get_column_letter

    validated = validate_stratum_codebook(codebook)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        validated.to_excel(
            writer,
            index=False,
            sheet_name="stratum_codebook",
        )
        worksheet = writer.sheets["stratum_codebook"]
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions
        worksheet.row_dimensions[1].height = 30

        for cell in worksheet[1]:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(
                horizontal="center",
                vertical="center",
                wrap_text=True,
            )

        for index, column in enumerate(validated.columns, start=1):
            values = validated[column].dropna().astype("string").unique()
            content_width = max(
                [len(str(column)), *(len(str(value)) for value in values)]
            )
            worksheet.column_dimensions[get_column_letter(index)].width = min(
                max(12, content_width + 2),
                30,
            )

        for cell in worksheet["A"][1:]:
            cell.number_format = "@"

    return output.resolve()


__all__ = [
    "MISSING_LEVEL",
    "export_stratum_codebook",
    "load_stratum_codebook",
    "validate_stratum_codebook",
]
