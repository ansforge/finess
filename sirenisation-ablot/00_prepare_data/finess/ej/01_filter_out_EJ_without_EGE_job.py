"""Filter FINESS EJ to the Stage 00 analysis scope."""

from __future__ import annotations


def run() -> None:
    import sys

    import pandas as pd

    from project_config import PATHS, PROJECT_ROOT

    stage_dir = PROJECT_ROOT / "00_prepare_data"
    if str(stage_dir) not in sys.path:
        sys.path.insert(0, str(stage_dir))

    from filtering_summary import update_filtering_summary
    from finess_scope import split_ej_analysis_scope

    ej = pd.read_parquet(PATHS.finess_ej_prepared)
    ege = pd.read_parquet(PATHS.finess_ege_prepared, columns=["nofinessej"])

    retained, excluded = split_ej_analysis_scope(ej, ege)

    PATHS.stage00_ej_filtered.parent.mkdir(parents=True, exist_ok=True)
    retained.to_parquet(PATHS.stage00_ej_filtered, index=False)
    excluded.to_parquet(PATHS.stage00_ej_excluded_without_ege, index=False)

    summary_path = PATHS.results / "00_prepare_data/filtering_summary.csv"
    update_filtering_summary(
        summary_path,
        entity_level="EJ",
        before_count=len(ej),
        retained_count=len(retained),
    )

    print(
        f"FINESS EJ scope: {len(retained):,} retained; "
        f"{len(excluded):,} excluded without a linked EGE."
    )
    print(f"- saved: {PATHS.stage00_ej_filtered}")
    print(f"- exclusions: {PATHS.stage00_ej_excluded_without_ege}")
    print(f"- filtering summary: {summary_path}")


if __name__ == "__main__":
    run()
