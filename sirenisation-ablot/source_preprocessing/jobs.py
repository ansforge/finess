"""Independent source-family preparation jobs and optional all-family runner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .adrien import (
    duplicate_rule_examples,
    prepare_adrien_candidates,
    prepare_adrien_ej,
    resolve_adrien_ege_duplicates,
)
from .ans import prepare_ans_ege, prepare_ans_ej, read_ans_sheets
from .finess import prepare_finess_ege, prepare_finess_ej

RAW_SNAPSHOTS = {
    "finess_ej_2026_05_04": "data/source/finess_entites_juridiques/raw/EntitesJuridiques_2026_05_04.csv",
    "finess_ege_structures_2026_05_04": "data/source/finess_etablissements/raw/Etablissements_2026_05_04.csv",
    "finess_ege_2026_05_04": "data/source/finess_etablissements/raw/EtablissementsGeolocalises_2026_05_04.csv",
    "ans_2026_07": "data/source/ANS/raw/juillet 2026/coherence_par_phase.xlsx",
    "adrien_initial_2026_06": "data/source/Adrien_Tortel/raw/df_sirets_initiaux_avec_concordances_2026_06.parquet",
    "adrien_proposals_2026_06": "data/source/Adrien_Tortel/raw/df_propositions_sirets_2026_06.parquet",
    "sirene_units_2026_06_01": "data/source/sirene_unites_legales/StockUniteLegale_2026_06_01.parquet",
    "sirene_establishments_2026_06_01": "data/source/sirene_etablissements/StockEtablissement_2026_06_01.parquet",
    "sirene_establishments_2026_07_01": "data/source/sirene_etablissements/StockEtablissement_2026_07_01.parquet",
}

CANONICAL_OUTPUTS = {
    "finess_ej": "data/source/finess_entites_juridiques/EntitesJuridiques_2026_05_04.parquet",
    "finess_ege": "data/source/finess_etablissements/EtablissementsGeolocalises_2026_05_04.parquet",
    "ans_ej": "data/source/ANS/df_ans_ej_valides.parquet",
    "ans_ege": "data/source/ANS/df_ans_ege_valides.parquet",
    "adrien_ej": "data/source/Adrien_Tortel/df_adrien_sirets_concordants_2026_06_sirenise.parquet",
    "adrien_ege": "data/source/Adrien_Tortel/df_adrien_sirets_concordants_2026_06_clean.parquet",
}

FAMILY_SNAPSHOTS = {
    "finess": ("finess_ej_2026_05_04", "finess_ege_2026_05_04"),
    "ans": ("ans_2026_07",),
    "adrien": ("adrien_initial_2026_06", "adrien_proposals_2026_06"),
}

FAMILY_OUTPUTS = {
    "finess": ("finess_ej", "finess_ege"),
    "ans": ("ans_ej", "ans_ege"),
    "adrien": ("adrien_ej", "adrien_ege"),
}


def _write_parquet(frame: pd.DataFrame, output_root: Path, relative_path: str) -> Path:
    output = output_root / relative_path
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(output, index=False)
    return output


def _raw_paths(project_root: Path, snapshot_names: tuple[str, ...]) -> dict[str, Path]:
    raw = {name: project_root / RAW_SNAPSHOTS[name] for name in snapshot_names}
    missing = {name: str(path) for name, path in raw.items() if not path.is_file()}
    if missing:
        raise FileNotFoundError(f"Named raw snapshots are missing: {missing}")
    return raw


def _family_result(
    frames: dict[str, pd.DataFrame], output_root: Path, **metadata: Any
) -> dict[str, Any]:
    paths = {
        name: _write_parquet(frame, output_root, CANONICAL_OUTPUTS[name])
        for name, frame in frames.items()
    }
    return {"paths": paths, "frames": frames, **metadata}


def run_finess_jobs(project_root: Path, output_root: Path) -> dict[str, Any]:
    """Prepare FINESS EJ/EGE products using only the two operational FINESS CSVs."""

    raw = _raw_paths(project_root, FAMILY_SNAPSHOTS["finess"])
    return _family_result(
        {
            "finess_ej": prepare_finess_ej(raw["finess_ej_2026_05_04"]),
            "finess_ege": prepare_finess_ege(raw["finess_ege_2026_05_04"]),
        },
        output_root,
    )


def run_ans_jobs(project_root: Path, output_root: Path) -> dict[str, Any]:
    """Prepare ANS EJ/EGE products using the named July ANS workbook."""

    raw = _raw_paths(project_root, FAMILY_SNAPSHOTS["ans"])
    ans_july = read_ans_sheets(raw["ans_2026_07"])
    return _family_result(
        {
            "ans_ej": prepare_ans_ej(ans_july),
            "ans_ege": prepare_ans_ege(ans_july),
        },
        output_root,
    )


def run_adrien_jobs(project_root: Path, output_root: Path) -> dict[str, Any]:
    """Prepare Adrien EJ/EGE products using only the two named June Parquets."""

    raw = _raw_paths(project_root, FAMILY_SNAPSHOTS["adrien"])
    candidates = prepare_adrien_candidates(
        raw["adrien_initial_2026_06"], raw["adrien_proposals_2026_06"]
    )
    adrien_ege, duplicate_summary = resolve_adrien_ege_duplicates(candidates)
    return _family_result(
        {
            "adrien_ej": prepare_adrien_ej(candidates),
            "adrien_ege": adrien_ege,
        },
        output_root,
        adrien_duplicate_summary=duplicate_summary,
        duplicate_examples=duplicate_rule_examples(),
    )


def run_family_jobs(
    family: str, project_root: Path, output_root: Path
) -> dict[str, Any]:
    """Run one source family without inspecting any unrelated family paths."""

    runners = {
        "finess": run_finess_jobs,
        "ans": run_ans_jobs,
        "adrien": run_adrien_jobs,
    }
    try:
        runner = runners[family]
    except KeyError as exc:
        raise ValueError(f"Unknown preprocessing family: {family!r}") from exc
    return runner(project_root, output_root)


def run_all_jobs(project_root: Path, output_root: Path) -> dict[str, Any]:
    """Regenerate the six canonical products beneath an isolated repository-style root."""

    finess = run_finess_jobs(project_root, output_root)
    ans = run_ans_jobs(project_root, output_root)
    adrien = run_adrien_jobs(project_root, output_root)
    return {
        "paths": {**finess["paths"], **ans["paths"], **adrien["paths"]},
        "frames": {**finess["frames"], **ans["frames"], **adrien["frames"]},
        "adrien_duplicate_summary": adrien["adrien_duplicate_summary"],
        "duplicate_examples": adrien["duplicate_examples"],
    }


def main() -> None:
    """Command-line entry point for an independent family or all families."""

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--family", choices=["finess", "ans", "adrien", "all"], required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()

    project_root = args.root.resolve()
    output_root = (
        args.output_root.resolve() if args.output_root is not None else project_root
    )

    result = (
        run_all_jobs(project_root, output_root)
        if args.family == "all"
        else run_family_jobs(args.family, project_root, output_root)
    )
    for name, path in result["paths"].items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
