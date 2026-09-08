"""Build the relationship-preserving development dataset from maintained inputs.

The development slice is defined only by ``SEED_EJS``. The builder verifies that
those EJ exist in FINESS, keeps all their FINESS EGE children, filters the ANS and
Adrien inputs to the same hierarchy, and retains the SIRENE records referenced by
those selected inputs. It does not depend on generated workflow results or human
review decisions.
"""

from __future__ import annotations

import argparse
import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# J'ai choisi des cas variés déjà examinés dans les résultats actuels
# Je suis parti des EGE, en supposant qu'on garde la même graine aléatoire pour leur clé aléatoire
SEED_EJS = {
    "070001862",  # 321102 ; EGE 070001458 : simple
    "920009271",  # 321102 ; EGE 920009297 : traité en vidéo
    "130029481",  # 321102 ; EGE 130029507 : traité en vidéo

    "370000820",  # 000100 ; EGE 370100208 : simple ; une des variables de stratification est <NA>
    "430002196",  # 000100 ; EGE 430002204 ; ne sera volontairement pas échantillonné dans le plan

    "2B0007314",  # 112120 ; EGE 2B0007322 ; simple ; possède une lettre dans son identifiant

    "330028309",  # 121000 ; EGE 330028358 : non trouvé (NA)

    "340017813",  # 122001 ; EGE 340020437 : trouvé hors ANS/Adrien
    "600000368",  # 122001 ; EGE 600101356 : trouvé hors ANS/Adrien, SIRET Initial manquant
    "750826604",  # 122001 ; EGE 470000175 ; ne sera volontairement pas échantillonné mais sera
                  # ajouté dans le dataset de cas EJ supplémentaires (siren retenu : 784809956)

    "350025623",  # 211000 ; EGE 350051264 : incertitude -12
                  #          EGE 350007324 : simple

    "530031319",  # 222210 ; EGE 530029800 : simple
    "930023080",  # 222210 ; EGE 930023098 : incertitude 12

    "010003739",   # EJ sans EGE exclu du périmètre de l'étude

    
}

SOURCE_ARTIFACTS = {
    "finess_ej": "data/source/finess_entites_juridiques/EntitesJuridiques_2026_05_04.parquet",
    "finess_ege": "data/source/finess_etablissements/EtablissementsGeolocalises_2026_05_04.parquet",
    "ans_ej": "data/source/ANS/df_ans_ej_valides.parquet",
    "ans_ege": "data/source/ANS/df_ans_ege_valides.parquet",
    "adrien_ej": "data/source/Adrien_Tortel/df_adrien_sirets_concordants_2026_06_sirenise.parquet",
    "adrien_ege": "data/source/Adrien_Tortel/df_adrien_sirets_concordants_2026_06_clean.parquet",
}

SIRENE_ARTIFACTS = {
    "establishments_june": "data/source/sirene_etablissements/StockEtablissement_2026_06_01.parquet",
    "establishments_july": "data/source/sirene_etablissements/StockEtablissement_2026_07_01.parquet",
    "units_june": "data/source/sirene_unites_legales/StockUniteLegale_2026_06_01.parquet",
}

REFERENCE_FILES = (
    "data/source/NAF/int_courts_naf_rev_2_clean.xlsx",
    "data/source/statut_juridique/statutjuridique_lib_2022_09.xlsx",
)


def canonical(value: Any) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text or None


def identifiers(values: Iterable[object], width: int) -> set[str]:
    return {
        text
        for value in values
        if (text := canonical(value)) is not None
        and len(text) == width
        and text.isdigit()
    }


def identifier_mask(frame: pd.DataFrame, column: str, accepted: set[str]) -> pd.Series:
    return frame[column].map(canonical).isin(accepted)


def business_references(frames: Iterable[pd.DataFrame]) -> tuple[set[str], set[str]]:
    """Collect SIREN/SIRET values referenced by selected maintained inputs.

    The prepared FINESS, ANS and Adrien inputs use several source-specific column
    names. Their stable semantic convention is that business-identifier columns
    contain ``siren`` or ``siret`` in the name. Width validation prevents flags,
    counts, or other similarly named fields from entering the closure.
    """

    siren_refs: set[str] = set()
    siret_refs: set[str] = set()
    for frame in frames:
        for column in frame.columns:
            name = str(column).lower()
            if "siret" in name:
                siret_refs.update(identifiers(frame[column], 14))
            elif "siren" in name:
                siren_refs.update(identifiers(frame[column], 9))
    siren_refs.update(siret[:9] for siret in siret_refs)
    return siren_refs, siret_refs


def write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.reset_index(drop=True).to_parquet(path, index=False)


def _required_paths(project_root: Path) -> dict[str, Path]:
    paths = {
        **{name: project_root / relative for name, relative in SOURCE_ARTIFACTS.items()},
        **{name: project_root / relative for name, relative in SIRENE_ARTIFACTS.items()},
    }
    paths.update({relative: project_root / relative for relative in REFERENCE_FILES})
    return paths


def build(project_root: Path, output_root: Path) -> None:
    project_root = project_root.resolve()
    output_root = output_root.resolve()
    seeds = set(SEED_EJS)

    required = _required_paths(project_root)
    missing = {name: str(path) for name, path in required.items() if not path.is_file()}
    if missing:
        raise FileNotFoundError(f"Missing source artifacts: {missing}")

    full = {
        name: pd.read_parquet(project_root / relative)
        for name, relative in SOURCE_ARTIFACTS.items()
    }

    finess_ej = full["finess_ej"].loc[
        lambda frame: identifier_mask(frame, "nofiness", seeds)
    ].copy()
    found_ejs = set(finess_ej["nofiness"].map(canonical).dropna())
    missing_ejs = sorted(seeds - found_ejs)
    if missing_ejs:
        raise ValueError(f"Configured EJ seeds are absent from FINESS: {missing_ejs}")

    finess_ege = full["finess_ege"].loc[
        lambda frame: identifier_mask(frame, "nofinessej", seeds)
    ].copy()
    ege_ids = set(finess_ege["nofinesset"].map(canonical).dropna())
    if not ege_ids:
        raise ValueError("Configured EJ seeds have no FINESS EGE children")

    selected = {
        "finess_ej": finess_ej,
        "finess_ege": finess_ege,
        "ans_ej": full["ans_ej"].loc[
            lambda frame: identifier_mask(frame, "nmfinessej_ej", seeds)
        ].copy(),
        "ans_ege": full["ans_ege"].loc[
            lambda frame: identifier_mask(frame, "nmfinessetab_stru", ege_ids)
            | identifier_mask(frame, "nmfinessej_ej", seeds)
        ].copy(),
        "adrien_ej": full["adrien_ej"].loc[
            lambda frame: identifier_mask(frame, "nofinessej", seeds)
        ].copy(),
        "adrien_ege": full["adrien_ege"].loc[
            lambda frame: identifier_mask(frame, "nofinesset", ege_ids)
            | identifier_mask(frame, "nofinessej", seeds)
        ].copy(),
    }

    output_paths = {
        SOURCE_ARTIFACTS[name]: frame for name, frame in selected.items()
    }
    for relative, frame in output_paths.items():
        write_parquet(frame, output_root / relative)

    siren_refs, siret_refs = business_references(selected.values())
    if not siren_refs and not siret_refs:
        raise ValueError("Selected FINESS/ANS/Adrien inputs contain no SIRENE references")

    june_establishments = pd.read_parquet(
        project_root / SIRENE_ARTIFACTS["establishments_june"],
        filters=[
            [("siret", "in", sorted(siret_refs))],
            [
                ("siren", "in", sorted(siren_refs)),
                ("etablissementSiege", "=", True),
            ],
        ],
    )
    july_establishments = pd.read_parquet(
        project_root / SIRENE_ARTIFACTS["establishments_july"],
        filters=[("siret", "in", sorted(siret_refs))],
    )
    units = pd.read_parquet(
        project_root / SIRENE_ARTIFACTS["units_june"],
        filters=[("siren", "in", sorted(siren_refs))],
    )

    write_parquet(
        june_establishments,
        output_root / SIRENE_ARTIFACTS["establishments_june"],
    )
    write_parquet(
        july_establishments,
        output_root / SIRENE_ARTIFACTS["establishments_july"],
    )
    write_parquet(units, output_root / SIRENE_ARTIFACTS["units_june"])

    found_sirets = identifiers(june_establishments["siret"], 14) | identifiers(
        july_establishments["siret"], 14
    )
    found_sirens = identifiers(units["siren"], 9)
    missing_sirets = sorted(siret_refs - found_sirets)
    missing_sirens = sorted(siren_refs - found_sirens)
    if missing_sirets or missing_sirens:
        raise ValueError(
            "SIRENE closure is incomplete: "
            f"missing SIRETs={missing_sirets}, missing SIRENs={missing_sirens}"
        )

    for relative in REFERENCE_FILES:
        destination = output_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(project_root / relative, destination)

    for root_name in ("study_inputs", "reviewed"):
        for level in ("ej", "ege"):
            (output_root / "data" / root_name / level).mkdir(
                parents=True,
                exist_ok=True,
            )

    (output_root / "results").mkdir(parents=True, exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    output_root = args.output_root or args.root / "dev"
    build(args.root, output_root)
    print(f"Development profile written to {output_root.resolve()}")


if __name__ == "__main__":
    main()
