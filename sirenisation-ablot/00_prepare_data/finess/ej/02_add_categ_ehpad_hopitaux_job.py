"""Add the hospital/EHPAD flag to in-scope FINESS EJ."""

from __future__ import annotations


def run() -> None:
    import sys

    import pandas as pd

    from project_config import PATHS, PROJECT_ROOT

    stage_dir = PROJECT_ROOT / "00_prepare_data"
    if str(stage_dir) not in sys.path:
        sys.path.insert(0, str(stage_dir))

    from finess_scope import add_hospital_ehpad_flag

    ej = pd.read_parquet(PATHS.stage00_ej_filtered)
    ege = pd.read_parquet(PATHS.finess_ege_prepared)

    enriched = add_hospital_ehpad_flag(ej, ege)

    PATHS.stage00_ej_prepared.parent.mkdir(parents=True, exist_ok=True)
    enriched.to_parquet(PATHS.stage00_ej_prepared, index=False)

    print(
        "Added hospital/EHPAD category: "
        f"{int(enriched['ehpad_hopitaux'].sum()):,} of {len(enriched):,} EJ(s) flagged."
    )
    print(f"- saved: {PATHS.stage00_ej_prepared}")


if __name__ == "__main__":
    run()
