"""Preparation jobs for the ANS July 2026 proposal extracts."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pandas as pd

COHERENCE_PRIORITY = (
    "Coherent_P1",
    "Coherent_P2",
    "Coherent_P3",
    "Coherent_Autres",
    "Incoherent",
    "Partiel_EJ",
)

ANS_EGE_SHEETS = (
    "Coherent_P1",
    "Coherent_P2",
    "Coherent_P3",
    "Coherent_Autres",
    "Incoherent",
    "Partiel_EG",
)

ANS_EJ_SHEETS = COHERENCE_PRIORITY


def read_ans_sheets(raw_path: Path) -> dict[str, pd.DataFrame]:
    """Read each operational sheet once and retain the source sheet name."""
    selected = list(dict.fromkeys((*ANS_EGE_SHEETS, *ANS_EJ_SHEETS)))
    sheets = pd.read_excel(raw_path, sheet_name=selected)
    missing = set(selected) - set(sheets)
    if missing:
        raise ValueError(f"{raw_path}: missing ANS sheets {sorted(missing)}")
    # Partial sheets carry ``cote_valide`` while the other sheets carry
    # ``statut_coherence``.  Pandas unioned those two optional fields in the
    # original workflow; all other fields must be shared.
    optional = {"cote_valide", "statut_coherence"}
    union = set().union(*(set(frame.columns) for frame in sheets.values()))
    shared = union - optional
    incompatible = {
        name: sorted(shared - set(frame.columns))
        for name, frame in sheets.items()
        if shared - set(frame.columns)
    }
    if incompatible:
        raise ValueError(f"{raw_path}: incompatible ANS sheet schemas {incompatible}")
    unexpected_optional = {
        name: sorted((set(frame.columns) - shared) - optional)
        for name, frame in sheets.items()
        if (set(frame.columns) - shared) - optional
    }
    if unexpected_optional:
        raise ValueError(
            f"{raw_path}: unexpected ANS sheet-specific columns {unexpected_optional}"
        )
    return sheets


def _combine_sheets(
    sheets: Mapping[str, pd.DataFrame], selected: tuple[str, ...]
) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for sheet_name in selected:
        part = sheets[sheet_name].copy()
        part["coherence"] = sheet_name
        parts.append(part)
    result = pd.concat(parts, ignore_index=True, sort=False)
    return result.loc[
        :, [column for column in result.columns if column != "coherence"] + ["coherence"]
    ]


def prepare_ans_ege(sheets: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """Union the July sheets accepted for establishment-level proposals."""
    result = _combine_sheets(sheets, ANS_EGE_SHEETS)
    required = {"nmfinessetab_stru", "siret_eg_retenu", "coherence"}
    missing = required - set(result.columns)
    if missing:
        raise ValueError(f"ANS EGE columns missing: {sorted(missing)}")
    return result


def _assert_constant_within_groups(
    source: pd.DataFrame, keys: list[str], columns: list[str]
) -> None:
    grouped = source.groupby(keys, sort=False, dropna=False)
    conflicts = {
        column: int((grouped[column].nunique(dropna=False) > 1).sum())
        for column in columns
    }
    conflicts = {name: count for name, count in conflicts.items() if count}
    if conflicts:
        raise ValueError(f"ANS EJ invariant conflicts: {conflicts}")


def prepare_ans_ej(sheets: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """Collapse July ANS rows to one explicit, validated EJ/SIREN record."""
    source = _combine_sheets(sheets, ANS_EJ_SHEETS)
    keys = ["nmfinessej_ej", "siren_ej_retenu"]
    invariant_columns = ["statut_ej", "phase_ej"]
    required = set(keys + invariant_columns + ["statut_eg", "phase_eg"])
    missing = required - set(source.columns)
    if missing:
        raise ValueError(f"ANS EJ columns missing: {sorted(missing)}")
    _assert_constant_within_groups(source, keys, invariant_columns)

    priority = {name: rank for rank, name in enumerate(COHERENCE_PRIORITY)}
    source = source.copy()
    source["_coherence_rank"] = source["coherence"].map(priority)
    if source["_coherence_rank"].isna().any():
        raise ValueError("ANS EJ contains an unknown coherence sheet")

    grouped = source.groupby(keys, sort=False, dropna=False)
    result = grouped.size().rename("ej_siren_pair_count").reset_index()

    first_rows = grouped.head(1).set_index(keys)
    result_index = pd.MultiIndex.from_frame(result[keys])
    for column in invariant_columns:
        result[column] = first_rows.loc[result_index, column].to_numpy()

    selected_rank = grouped["_coherence_rank"].min()
    labels_by_rank = {rank: name for name, rank in priority.items()}
    result["coherence"] = [labels_by_rank[int(value)] for value in selected_rank]

    group_index = source.set_index(keys).index
    metric_specs = {
        "statut_eg_valide_fort_proportion": source["statut_eg"].eq("VALIDE_FORT"),
        "statut_eg_valide_proportion": source["statut_eg"].eq("VALIDE"),
        "phase_eg_1_proportion": source["phase_eg"].eq(1),
        "phase_eg_2_proportion": source["phase_eg"].eq(2),
        "phase_eg_3_proportion": source["phase_eg"].eq(3),
    }
    for output_name, values in metric_specs.items():
        values = pd.Series(values.to_numpy(), index=group_index)
        result[output_name] = values.groupby(level=[0, 1], sort=False).mean().to_numpy()

    ordered = keys + [
        "ej_siren_pair_count",
        "coherence",
        "statut_ej",
        "phase_ej",
        "statut_eg_valide_fort_proportion",
        "statut_eg_valide_proportion",
        "phase_eg_1_proportion",
        "phase_eg_2_proportion",
        "phase_eg_3_proportion",
    ]
    result = result.loc[:, ordered]
    if result["nmfinessej_ej"].duplicated().any():
        raise ValueError("ANS EJ does not resolve to one row per FINESS EJ")
    return result
