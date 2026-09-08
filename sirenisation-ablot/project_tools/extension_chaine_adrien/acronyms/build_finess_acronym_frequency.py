from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path

import pandas as pd

from project_config import PATHS

DEFAULT_INPUT = PATHS.finess_ege_prepared
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "output/finess_acronym_frequency.xlsx"

EGE_COLUMN = "nofinesset"
NAME_COLUMN = "rs"
MAX_TOKEN_LENGTH = 8
TOP_N = 1000

STOPWORDS = {
    "LE",
    "LA",
    "LES",
    "UN",
    "UNE",
    "DE",
    "DU",
    "DES",
    "D",
    "L",
    "AUX",
    "AU",
    "SUR",
    "SOUS",
    "CHEZ",
    "SAINT",
    "SAINTE",
    "ST",
    "STE",
}

TOKEN_RE = re.compile(r"[A-Z0-9]+")
PREFIX_RE = re.compile(r"\b(?:D'|L'|D |L )")


def normalize_name(value: object) -> str | None:
    if pd.isna(value):
        return None

    text = str(value).translate(
        str.maketrans({"ª": " ", "º": " ", "Ǝ": "E", "Ƨ": "S", "Η": "H", "Π": "P", "Ҫ": "C", "": " "})
    )
    text = (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
        .upper()
    )
    text = PREFIX_RE.sub("", text)
    text = "".join(" " if unicodedata.category(char).startswith("P") else char for char in text)
    text = re.sub(r"\s+", " ", text).strip()

    words = [word for word in text.split() if word not in STOPWORDS]
    return " ".join(words) or None


def build_frequency_table(frame: pd.DataFrame) -> pd.DataFrame:
    tokens: list[str] = []
    for value in frame[NAME_COLUMN]:
        normalized = normalize_name(value)
        if not normalized:
            continue
        tokens.extend(
            token
            for token in TOKEN_RE.findall(normalized)
            if 1 <= len(token) <= MAX_TOKEN_LENGTH
        )

    if not tokens:
        return pd.DataFrame(columns=["token", "length", "occurrences"])

    token_series = pd.Series(tokens, dtype="string", name="token")
    result = (
        token_series.value_counts()
        .rename_axis("token")
        .rename("occurrences")
        .reset_index()
    )
    result["length"] = result["token"].str.len()
    return (
        result[["token", "length", "occurrences"]]
        .sort_values(["occurrences", "token"], ascending=[False, True], kind="mergesort")
        .head(TOP_N)
        .reset_index(drop=True)
    )


def run(input_path: Path, output_path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(input_path, columns=[EGE_COLUMN, NAME_COLUMN])

    if frame[EGE_COLUMN].isna().any():
        raise ValueError(f"{input_path} contains missing {EGE_COLUMN} values.")

    duplicate_count = int(frame[EGE_COLUMN].duplicated().sum())
    if duplicate_count:
        print(
            f"{duplicate_count:,} duplicate {EGE_COLUMN} rows found; "
            "only the first row for each EGE is retained."
        )

    frame = frame.drop_duplicates(subset=[EGE_COLUMN], keep="first")
    result = build_frequency_table(frame)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_excel(output_path, index=False, sheet_name="acronym_frequency")

    print(f"EGE analyzed: {len(frame):,}")
    print(f"Tokens exported: {len(result):,}")
    print(f"Saved to: {output_path}")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a FINESS short-token frequency table for acronym review."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run(args.input, args.output)


if __name__ == "__main__":
    main()
