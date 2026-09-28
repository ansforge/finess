"""Preparation jobs for the May 2026 FINESS snapshots.

The FINESS EGE preprocessing logic is adapted in part from work by Jean-Claude Arbaut.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tempfile import TemporaryFile

import pandas as pd

FINESS_EJ_HEADERS = [
    "structureej",
    "nofiness",
    "rs",
    "rslongue",
    "complrs",
    "numvoie",
    "typvoie",
    "voie",
    "compvoie",
    "compldistrib",
    "lieuditbp",
    "commune",
    "ligneacheminement",
    "departement",
    "libdepartement",
    "telephone",
    "statutjuridique",
    "libstatutjuridique",
    "categetab",
    "libcategetab",
    "siren",
    "codeape",
    "datecrea",
]

FINESS_EGE_HEADERS = [
    "nofinesset",
    "nofinessej",
    "rs",
    "rslongue",
    "complrs",
    "compldistrib",
    "numvoie",
    "typvoie",
    "voie",
    "compvoie",
    "lieuditbp",
    "commune",
    "departement",
    "libdepartement",
    "ligneacheminement",
    "telephone",
    "telecopie",
    "categetab",
    "libcategetab",
    "categagretab",
    "libcategagretab",
    "siret",
    "codeape",
    "codemft",
    "libmft",
    "codesph",
    "libsph",
    "dateouv",
    "dateautor",
    "datemaj",
    "numuai",
]

FINESS_GEO_HEADERS = [
    "nofinesset",
    "coordxet",
    "coordyet",
    "sourcecoordet",
    "datemaj_coord",
]


def prepare_finess_ej(raw_path: Path) -> pd.DataFrame:
    """Read the named May 2026 FINESS EJ CSV without losing leading zeroes."""
    result = pd.read_csv(
        raw_path,
        sep=";",
        skiprows=1,
        header=None,
        names=FINESS_EJ_HEADERS,
        dtype=str,
        encoding="utf-8-sig",
        keep_default_na=False,
    )
    if result.shape[1] != len(FINESS_EJ_HEADERS):
        raise ValueError(
            f"{raw_path}: expected {len(FINESS_EJ_HEADERS)} columns, "
            f"found {result.shape[1]}"
        )
    if not result["structureej"].eq("structureej").all():
        raise ValueError(f"{raw_path}: unexpected FINESS EJ row type")
    result = result.drop(columns="structureej")
    if result["nofiness"].duplicated().any():
        raise ValueError(f"{raw_path}: nofiness is not unique")
    return result


def prepare_finess_ege(raw_path: Path) -> pd.DataFrame:
    """Split and merge the structure/geolocation records in the FINESS export."""
    with TemporaryFile(mode="w+t", encoding="utf-8") as structures, TemporaryFile(
        mode="w+t", encoding="utf-8"
    ) as coordinates:
        structure_count = 0
        coordinate_count = 0
        with raw_path.open("rt", encoding="utf-8") as source:
            for line_number, line in enumerate(source, start=1):
                if line.startswith("structureet;"):
                    structures.write(line)
                    structure_count += 1
                elif line.startswith("geolocalisation;"):
                    coordinates.write(line)
                    coordinate_count += 1
                elif not line.startswith("finess;etalab;"):
                    raise ValueError(
                        f"{raw_path}:{line_number}: unexpected FINESS row type"
                    )

        if structure_count != coordinate_count:
            raise ValueError(
                f"{raw_path}: {structure_count} structures but "
                f"{coordinate_count} geolocations"
            )

        structures.seek(0)
        coordinates.seek(0)
        structure_df = pd.read_csv(
            structures, sep=";", header=None, dtype=str
        ).drop(columns=0)
        coordinate_df = pd.read_csv(
            coordinates, sep=";", header=None, dtype=str
        ).drop(columns=0)

    if structure_df.shape[1] != len(FINESS_EGE_HEADERS):
        raise ValueError(f"{raw_path}: unexpected structure schema")
    if coordinate_df.shape[1] != len(FINESS_GEO_HEADERS):
        raise ValueError(f"{raw_path}: unexpected geolocation schema")

    structure_df.columns = FINESS_EGE_HEADERS
    coordinate_df.columns = FINESS_GEO_HEADERS
    if not structure_df["nofinesset"].equals(coordinate_df["nofinesset"]):
        raise ValueError(f"{raw_path}: structure/geolocation order differs")

    result = structure_df.merge(
        coordinate_df,
        on="nofinesset",
        how="inner",
        validate="one_to_one",
    )
    if len(result) != structure_count:
        raise ValueError(f"{raw_path}: merge lost FINESS establishment rows")

    result[["coordxet", "coordyet"]] = result[["coordxet", "coordyet"]].apply(
        pd.to_numeric, errors="coerce"
    )
    date_columns = ["dateouv", "dateautor", "datemaj", "datemaj_coord"]
    # Parse directly to microseconds. Some source rows contain syntactically valid
    # dates with years before pandas' nanosecond lower bound (for example 0787);
    # parsing through datetime64[ns] would coerce them to NaT.
    def parse_microsecond_dates(values: pd.Series) -> pd.Series:
        parsed = []
        for value in values:
            try:
                parsed.append(
                    datetime.strptime(value, "%Y-%m-%d")  # noqa: DTZ007
                )
            except (TypeError, ValueError):
                parsed.append(pd.NaT)

        return pd.Series(parsed, index=values.index, dtype="datetime64[us]")

    for column in date_columns:
        result[column] = parse_microsecond_dates(result[column])
    string_columns = result.select_dtypes(include=["object", "string"]).columns
    result[string_columns] = result[string_columns].fillna("")
    if result["nofinesset"].duplicated().any():
        raise ValueError(f"{raw_path}: nofinesset is not unique")
    return result
