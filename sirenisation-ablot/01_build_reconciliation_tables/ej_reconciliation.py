"""EJ-specific Stage 01 reconciliation transformations."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from reconciliation_job_helpers import (
    format_naf_code,
    join_nonempty,
    normalize_integer_code,
    select_and_order_columns,
)

SCM_SEL = {"79", "85", "86", "87", "91"}

FINAL_COLUMN_ORDER = [
    "EJ",
    "candidate_rank",
    "proposal_source",
    "is_initial_siren",
    "etat_siren",
    "siren_proposal",
    "finess__rs",
    "sirene__denominationUniteLegale",
    "finess__adresse_admin",
    "finess__codeape",
    "finess__intitule_naf",
    "sirene__activitePrincipaleUniteLegale",
    "sirene__intitule_naf",
    "finess__rslongue",
    "sirene__denominationUsuelle1UniteLegale",
    "finess__statutjuridique",
    "finess__libstatutjuridique",
    "sirene__categorieJuridiqueUniteLegale",
    "sirene__libstatutjuridique",
    "finess__datecrea",
    "sirene__dateCreationUniteLegale",
    "coherence_EJ_ANS",
    "statut_EJ_ANS",
    "is_initial_siren_ANS",
    "statut_validation_Adrien",
    "datasets_consistency",
    "secteur_EJ",
    "random_key",
]


def _random_key(ej: Any) -> Any:
    if pd.isna(ej):
        return pd.NA
    fragment = str(ej)[2:9]
    if not fragment:
        return pd.NA
    try:
        return round((float(fragment) / math.pi) % 1, 6)
    except ValueError:
        return pd.NA


def _finess_address(row: pd.Series) -> Any:
    address = join_nonempty(
        [
            row.get("finess__numvoie"),
            row.get("finess__typvoie"),
            row.get("finess__voie"),
            row.get("finess__compvoie"),
            row.get("finess__compldistrib"),
            row.get("finess__lieuditbp"),
            row.get("finess__ligneacheminement"),
        ]
    )
    return address if address else pd.NA


def add_derived_columns(enriched_table: pd.DataFrame) -> pd.DataFrame:
    """Add the EJ variables used for stratification and deterministic review order."""
    out = enriched_table.copy()
    attrs = dict(enriched_table.attrs)

    out["random_key"] = pd.Series(
        out["EJ"].map(_random_key),
        index=out.index,
        dtype="Float64",
    )
    out["finess__adresse_admin"] = pd.Series(
        out.apply(_finess_address, axis=1),
        index=out.index,
        dtype="string",
    )
    out["coherence_EJ_ANS"] = pd.Series(
        np.select(
            [
                out["dataset1__coherence"].isna(),
                out["dataset1__coherence"].isin(
                    ["Coherent_P1", "Coherent_P2", "Coherent_P3", "Coherent_Autres"]
                ),
                out["dataset1__coherence"].eq("Incoherent"),
                out["dataset1__coherence"].eq("Partiel_EJ"),
            ],
            [pd.NA, "Cohérent", "Incohérent", "EJ seul"],
            default="Erreur",
        ),
        index=out.index,
        dtype="string",
    )
    out["is_initial_siren_ANS"] = pd.Series(
        np.select(
            [
                out["dataset1__siren"].isna(),
                out["dataset1__siren"].notna() & out["finess__siren"].isna(),
                (
                    out["dataset1__siren"].notna()
                    & out["finess__siren"].notna()
                    & out["dataset1__siren"].eq(out["finess__siren"])
                ),
                (
                    out["dataset1__siren"].notna()
                    & out["finess__siren"].notna()
                    & out["dataset1__siren"].ne(out["finess__siren"])
                ),
            ],
            [pd.NA, False, True, False],
            default=pd.NA,
        ),
        index=out.index,
        dtype="boolean",
    )
    out["statut_validation_Adrien"] = pd.Series(
        np.select(
            [
                out["dataset2__proposal_count"].isna(),
                out["dataset2__proposal_count"].eq(0),
                out["dataset2__proposal_count"].eq(1),
                out["dataset2__proposal_count"].ge(2),
            ],
            [pd.NA, "0 proposition", "1 proposition", "2+ propositions"],
            default="Erreur",
        ),
        index=out.index,
        dtype="string",
    )
    out["secteur_EJ"] = pd.Series(
        np.select(
            [
                out["finess__ehpad_hopitaux"].isna(),
                out["finess__ehpad_hopitaux"].eq(True),
                out["finess__statutjuridique"].isna(),
                out["finess__statutjuridique"].astype("string").isin(SCM_SEL),
            ],
            ["Erreur", "ehpad_hopitaux", "Erreur", "scm_sel"],
            default="autre",
        ),
        index=out.index,
        dtype="string",
    )

    out.attrs.update(attrs)
    return out



def finalize_enriched_consistency(enriched_table: pd.DataFrame) -> pd.DataFrame:
    """Publish the EJ consistency table with downstream public column names only."""
    required_internal = {
        "dataset1__statut_ej",
        "consistency_type",
    }
    missing = required_internal.difference(enriched_table.columns)
    if missing:
        raise KeyError(
            "EJ enriched consistency is missing columns that must be published "
            f"under public names: {sorted(missing)}"
        )

    out = enriched_table.rename(
        columns={
            "dataset1__statut_ej": "statut_EJ_ANS",
            "consistency_type": "datasets_consistency",
        }
    ).copy()

    obsolete = {"dataset1__statut_ej", "consistency_type"}.intersection(out.columns)
    if obsolete:
        raise ValueError(
            f"Obsolete Stage 01 column names remain after renaming: {sorted(obsolete)}"
        )
    return out


def finalize_proposals(
    proposal_table: pd.DataFrame,
    *,
    legal_status_labels: pd.Series,
    naf_labels: pd.Series,
) -> pd.DataFrame:
    """Apply EJ reference labels, public names/status values and stable column order."""
    out = proposal_table.copy()

    out["sirene__categorieJuridiqueUniteLegale"] = normalize_integer_code(
        out["sirene__categorieJuridiqueUniteLegale"]
    )
    out["sirene__libstatutjuridique"] = (
        out["sirene__categorieJuridiqueUniteLegale"].map(legal_status_labels)
    )

    finess_naf = "finess__codeape"
    sirene_naf = "sirene__activitePrincipaleUniteLegale"
    out[finess_naf] = format_naf_code(out[finess_naf])
    out[sirene_naf] = format_naf_code(out[sirene_naf])
    out["finess__intitule_naf"] = out[finess_naf].map(naf_labels)
    out["sirene__intitule_naf"] = out[sirene_naf].map(naf_labels)

    out = out.rename(
        columns={
            "dataset1__statut_ej": "statut_EJ_ANS",
            "consistency_type": "datasets_consistency",
            "sirene__etatAdministratifUniteLegale": "etat_siren",
        }
    )
    if out.columns.duplicated().any():
        duplicates = out.columns[out.columns.duplicated()].tolist()
        raise ValueError(f"Duplicate columns after final renaming: {duplicates}")

    out["etat_siren"] = (
        out["etat_siren"].astype("string").replace({"A": "", "C": "Cessé"})
    )
    return select_and_order_columns(out, FINAL_COLUMN_ORDER)
