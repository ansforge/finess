"""Filter FINESS EGE to establishments whose parent EJ exists in FINESS."""

from __future__ import annotations


def run() -> None:
    import sys

    import pandas as pd

    from project_config import PATHS, PROJECT_ROOT

    stage_dir = PROJECT_ROOT / "00_prepare_data"
    if str(stage_dir) not in sys.path:
        sys.path.insert(0, str(stage_dir))

    from filtering_summary import update_filtering_summary
    from finess_scope import filter_ege_to_known_parents

    ege = pd.read_parquet(PATHS.finess_ege_prepared)
    ej = pd.read_parquet(PATHS.finess_ej_prepared, columns=["nofiness"])

    retained = filter_ege_to_known_parents(ege, ej)
    removed_count = len(ege) - len(retained)

    PATHS.stage00_ege_prepared.parent.mkdir(parents=True, exist_ok=True)
    retained.to_parquet(PATHS.stage00_ege_prepared, index=False)

    summary_path = PATHS.results / "00_prepare_data/filtering_summary.csv"
    update_filtering_summary(
        summary_path,
        entity_level="EGE",
        before_count=len(ege),
        retained_count=len(retained),
    )

    print(
        f"FINESS EGE scope: {len(retained):,} retained; "
        f"{removed_count:,} excluded without a known parent EJ."
    )
    print(f"- saved: {PATHS.stage00_ege_prepared}")
    print(f"- filtering summary: {summary_path}")


if __name__ == "__main__":
    run()
