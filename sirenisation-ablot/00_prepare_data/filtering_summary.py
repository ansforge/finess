"""Small reporting helper for the Stage 00 FINESS scope filters."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

SUMMARY_COLUMNS = [
    "Entity level",
    "Entities before filtering",
    "Entities filtered out",
    "Entities retained after filtering",
]
ENTITY_LABELS = {
    "EJ": "EJ (FINESS legal entities)",
    "EGE": "EGE (FINESS geographical establishments)",
}


def update_filtering_summary(
    output_path: str | Path,
    *,
    entity_level: str,
    before_count: int,
    retained_count: int,
) -> Path:
    """Insert or replace one entity-level row in the shared Stage 00 summary."""

    if entity_level not in ENTITY_LABELS:
        raise ValueError(f"Unsupported entity level: {entity_level!r}")

    before_count = int(before_count)
    retained_count = int(retained_count)
    if before_count < 0 or retained_count < 0 or retained_count > before_count:
        raise ValueError(
            "Filtering counts must satisfy 0 <= retained_count <= before_count"
        )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    label = ENTITY_LABELS[entity_level]
    row = pd.DataFrame(
        [
            {
                "Entity level": label,
                "Entities before filtering": before_count,
                "Entities filtered out": before_count - retained_count,
                "Entities retained after filtering": retained_count,
            }
        ],
        columns=SUMMARY_COLUMNS,
    )

    if output.exists():
        existing = pd.read_csv(output)
        if list(existing.columns) != SUMMARY_COLUMNS:
            raise ValueError(
                f"Existing filtering summary has an unexpected schema: {output}"
            )
        existing = existing.loc[existing["Entity level"].ne(label)]
        summary = pd.concat([existing, row], ignore_index=True)
    else:
        summary = row

    order = {label: index for index, label in enumerate(ENTITY_LABELS.values())}
    summary = summary.sort_values(
        "Entity level", key=lambda values: values.map(order)
    ).reset_index(drop=True)
    summary.to_csv(output, index=False, encoding="utf-8")
    return output.resolve()
