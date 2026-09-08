"""Optionally add supplementary EGE confirmed decisions to the current review.

Current-review decisions are authoritative on overlap. Supplementary decisions that
do not overlap are appended, and the combined set is published as the all-confirmed
Stage 04 output.
"""

from __future__ import annotations


def run() -> dict[str, object]:
    import sys

    import pandas as pd

    from project_config import PATHS, PROJECT_ROOT

    module_dir = PROJECT_ROOT / "04_merge_reviews"
    if str(module_dir) not in sys.path:
        sys.path.insert(0, str(module_dir))

    import merge_reviews as mrp

    config = mrp.EGE_SIRET_CONFIG
    current_path = PATHS.stage04_ege_confirmed
    additional_path = PATHS.ege_additional_decisions
    all_confirmed_output = PATHS.stage04_ege_all_confirmed
    all_confirmed_excel = all_confirmed_output.with_suffix(".xlsx")

    current = pd.read_parquet(current_path)
    additional = pd.read_excel(
        additional_path,
        dtype="string",
        keep_default_na=False,
    )

    pooled_frame = pd.read_parquet(
        PATHS.stage02_ege_pooled_proposals,
        columns=["EGE"],
    )
    validated_additional = mrp.validate_confirmed_decision_table(
        additional,
        config=config,
        source=additional_path.name,
    )
    mrp.validate_confirmed_entities_in_reference(
        validated_additional,
        pooled_frame,
        config=config,
        source=additional_path.name,
    )

    result = mrp.combine_confirmed_decision_sets(
        current,
        additional,
        config=config,
        additional_source=additional_path.name,
    )

    mrp.export_dataframe(result.combined_decisions, all_confirmed_output)
    mrp.export_dataframe(result.combined_decisions, all_confirmed_excel)

    print("EGE additional confirmed decisions")
    print(f"- current review decisions: {len(current):,}")
    print(f"- supplementary decisions: {len(result.additional_decisions):,}")
    print(f"- supplementary-only EGE: {len(result.additional_only_entities):,}")
    print(f"- identical overlaps: {len(result.identical_overlaps):,}")
    print(f"- combined confirmed decisions: {len(result.combined_decisions):,}")
    print("- saved:")
    print(f"  - {all_confirmed_output}")
    print(f"  - {all_confirmed_excel}")

    if result.conflicting_overlaps:
        preview = ", ".join(result.conflicting_overlaps[:20])
        suffix = " ..." if len(result.conflicting_overlaps) > 20 else ""
        print(
            "Warning: "
            f"{len(result.conflicting_overlaps):,} conflicting EGE overlap(s) "
            "were found between the current review and supplementary decisions. "
            f"The current-review decision was kept. Examples: {preview}{suffix}"
        )
    else:
        print("Additional-decision merge: no conflicting overlaps found.")

    return {
        "current_decisions": current,
        "additional_decisions": result.additional_decisions,
        "combined_decisions": result.combined_decisions,
        "identical_overlaps": result.identical_overlaps,
        "conflicting_overlaps": result.conflicting_overlaps,
        "additional_only_entities": result.additional_only_entities,
        "output_paths": [all_confirmed_output, all_confirmed_excel],
    }


if __name__ == "__main__":
    run()
