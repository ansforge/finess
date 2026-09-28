"""EGE-specific Stage 01 reconciliation transformations."""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np
import pandas as pd
from finess_sirene_reconciliation import validated_parent_enrichment
from reconciliation_job_helpers import (
    assert_unique_key,
    format_naf_code,
    join_nonempty,
    normalize_identifier_series,
    select_and_order_columns,
)

RANDOM_KEY_SEED = "EGE-2026-07"

FINAL_COLUMN_ORDER = [
    "EGE",
    "candidate_rank",
    "proposal_source",
    "is_initial_siret",
    "etat_siret",
    "siret_proposal",
    "EGE__rs",
    "EGE__rslongue",
    "EGE__codeape",
    "EGE__intitule_naf",
    "EGE__dateouv",
    "EGE__adresse",
    "siret__enseigne1Etablissement",
    "siret__denominationUsuelleEtablissement",
    "siret__activitePrincipaleEtablissement",
    "siret__intitule_naf",
    "siret__dateCreationEtablissement",
    "siret__adresse",
    "siren__denominationUniteLegale",
    "datasets_consistency_EGE",
    "coherence_EGE_ANS",
    "statut_EGE_ANS",
    "statut_validation_Adrien_EGE",
    "coherence_siren_du_siret_avec_siren_ej_corrige",
    "EJ",
    "siren_ej_corrige",
    "EJ__rs",
    "EJ__datasets_consistency",
    "EJ__coherence_EJ_ANS",
    "EJ__statut_EJ_ANS",
    "EJ__is_initial_siren_ANS",
    "EJ__statut_validation_Adrien",
    "EJ__secteur_EJ",
    "stratum_id",
    "random_key",
]


def _random_key(entity_id: Any) -> Any:
    if pd.isna(entity_id):
        return pd.NA
    payload = f"{RANDOM_KEY_SEED}|{str(entity_id).strip()}".encode()
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    return int.from_bytes(digest, byteorder="big", signed=False)


def _finess_address(row: pd.Series) -> Any:
    street = join_nonempty(
        [
            row.get("finess__numvoie"),
            row.get("finess__typvoie"),
            row.get("finess__voie"),
            row.get("finess__compvoie"),
        ]
    )
    distribution = join_nonempty(
        [
            row.get("finess__compldistrib"),
            row.get("finess__lieuditbp"),
        ]
    )
    routing = join_nonempty([row.get("finess__ligneacheminement")])
    lines = [value for value in [street, distribution, routing] if value]
    return " ".join(dict.fromkeys(lines)) if lines else pd.NA


def add_derived_columns(enriched_table: pd.DataFrame) -> pd.DataFrame:
    """Add EGE review-order and stratification variables before parent enrichment."""
    out = enriched_table.copy()
    attrs = dict(enriched_table.attrs)

    out["random_key"] = pd.Series(
        out["EGE"].map(_random_key),
        index=out.index,
        dtype="UInt64",
    )
    out["finess__adresse"] = pd.Series(
        out.apply(_finess_address, axis=1),
        index=out.index,
        dtype="string",
    )
    out["coherence_EGE_ANS"] = pd.Series(
        np.select(
            [
                out["dataset1__coherence"].isna(),
                out["dataset1__coherence"].isin(
                    ["Coherent_P1", "Coherent_P2", "Coherent_P3", "Coherent_Autres"]
                ),
                out["dataset1__coherence"].eq("Incoherent"),
                out["dataset1__coherence"].eq("Partiel_EG"),
            ],
            [pd.NA, "Cohérent", "Incohérent", "EGE seul"],
            default="Erreur",
        ),
        index=out.index,
        dtype="string",
    )
    out["is_initial_siret_ANS"] = pd.Series(
        np.select(
            [
                out["dataset1__siret"].isna(),
                out["dataset1__siret"].notna() & out["finess__siret"].isna(),
                (
                    out["dataset1__siret"].notna()
                    & out["finess__siret"].notna()
                    & out["dataset1__siret"].eq(out["finess__siret"])
                ),
                (
                    out["dataset1__siret"].notna()
                    & out["finess__siret"].notna()
                    & out["dataset1__siret"].ne(out["finess__siret"])
                ),
            ],
            [pd.NA, False, True, False],
            default=pd.NA,
        ),
        index=out.index,
        dtype="boolean",
    )
    out["statut_validation_Adrien_EGE"] = pd.Series(
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

    out.attrs.update(attrs)
    return out


def attach_parent_ej_context(
    enriched_table: pd.DataFrame,
    ej_enrichment_raw: pd.DataFrame,
) -> pd.DataFrame:
    """Attach validated parent-EJ context, including the inherited stratum."""
    inherited_columns = [
        "finess__rs",
        "coherence_EJ_ANS",
        "statut_EJ_ANS",
        "is_initial_siren_ANS",
        "statut_validation_Adrien",
        "datasets_consistency",
        "secteur_EJ",
        "stratum_id",
    ]
    renames = {
        "finess__rs": "EJ__rs",
        "coherence_EJ_ANS": "EJ__coherence_EJ_ANS",
        "statut_EJ_ANS": "EJ__statut_EJ_ANS",
        "is_initial_siren_ANS": "EJ__is_initial_siren_ANS",
        "statut_validation_Adrien": "EJ__statut_validation_Adrien",
        "datasets_consistency": "EJ__datasets_consistency",
        "secteur_EJ": "EJ__secteur_EJ",
    }

    ej_enrichment = (
        validated_parent_enrichment(
            ej_enrichment_raw,
            parent_column="EJ",
            inherited_columns=inherited_columns,
            source="EJ stratified proposals",
        )
        .rename(columns=renames)
    )
    ej_enrichment["EJ"] = normalize_identifier_series(ej_enrichment["EJ"], 9)
    assert_unique_key(ej_enrichment, "EJ", "EJ enrichment dataset")

    out = enriched_table.rename(columns={"finess__nofinessej": "EJ"}).copy()
    out["EJ"] = normalize_identifier_series(out["EJ"], 9)
    attrs = dict(enriched_table.attrs)

    out = out.merge(
        ej_enrichment,
        on="EJ",
        how="left",
        validate="many_to_one",
        indicator="_ej_enrichment_merge",
    )
    out["has_ej_enrichment"] = out["_ej_enrichment_merge"].eq("both")
    out = out.drop(columns="_ej_enrichment_merge")
    out.attrs.update(attrs)

    if "stratum_id" not in out.columns:
        raise KeyError(
            "stratum_id was not found after EJ enrichment. "
            "Check the EJ stratified proposal source."
        )
    return out


def _siret_address(row: pd.Series) -> Any:
    address = join_nonempty(
        [
            row.get("siret__numeroVoieEtablissement"),
            row.get("siret__indiceRepetitionEtablissement"),
            row.get("siret__typeVoieEtablissement"),
            row.get("siret__libelleVoieEtablissement"),
            row.get("siret__codePostalEtablissement"),
            row.get("siret__libelleCommuneEtablissement"),
        ]
    )
    return address if address else pd.NA


def prepare_proposals(
    proposal_table: pd.DataFrame,
    *,
    naf_labels: pd.Series,
) -> pd.DataFrame:
    """Rename source prefixes, build SIRET addresses and add NAF labels."""
    prefix_renames = {
        column: column.replace("finess__", "EGE__", 1)
        for column in proposal_table.columns
        if column.startswith("finess__")
    }
    prefix_renames.update(
        {
            column: column.replace("sirene__", "siret__", 1)
            for column in proposal_table.columns
            if column.startswith("sirene__")
        }
    )

    out = proposal_table.rename(columns=prefix_renames).copy()
    if out.columns.duplicated().any():
        duplicates = out.columns[out.columns.duplicated()].tolist()
        raise ValueError(f"Duplicate columns after prefix renaming: {duplicates}")

    out["siret__adresse"] = pd.Series(
        out.apply(_siret_address, axis=1),
        index=out.index,
        dtype="string",
    )

    ege_naf = "EGE__codeape"
    siret_naf = "siret__activitePrincipaleEtablissement"
    for column in (ege_naf, siret_naf):
        if column not in out.columns:
            raise KeyError(f"{column!r} is required for NAF enrichment.")

    out[ege_naf] = format_naf_code(out[ege_naf])
    out[siret_naf] = format_naf_code(out[siret_naf])
    out["EGE__intitule_naf"] = out[ege_naf].map(naf_labels)
    out["siret__intitule_naf"] = out[siret_naf].map(naf_labels)
    return out


def sirens_from_siret_proposals(proposal_table: pd.DataFrame) -> list[str]:
    """Return distinct valid SIREN prefixes from 14-digit proposed SIRET."""
    siret = proposal_table["siret_proposal"].astype("string")
    siren = siret.where(siret.str.fullmatch(r"\d{14}", na=False)).str[:9]
    return sorted(siren.dropna().drop_duplicates().tolist())


def attach_siren_denomination(
    proposal_table: pd.DataFrame,
    siren_df: pd.DataFrame,
) -> pd.DataFrame:
    """Attach legal-unit denomination from the SIREN prefix of each proposed SIRET."""
    out = proposal_table.copy()
    attrs = dict(proposal_table.attrs)

    siret = out["siret_proposal"].astype("string")
    out["siren"] = siret.where(siret.str.fullmatch(r"\d{14}", na=False)).str[:9]

    lookup = siren_df[["siren", "denominationUniteLegale"]].copy()
    lookup["siren"] = normalize_identifier_series(lookup["siren"], 9)
    lookup = lookup.dropna(subset=["siren"]).drop_duplicates(subset=["siren"], keep="first")
    assert_unique_key(lookup, "siren", "SIREN dataset")

    out["siren__denominationUniteLegale"] = out["siren"].map(
        lookup.set_index("siren")["denominationUniteLegale"]
    )
    out.attrs.update(attrs)
    return out


def attach_corrected_ej_reference(
    proposal_table: pd.DataFrame,
    ej_decisions: pd.DataFrame,
) -> pd.DataFrame:
    """Attach the retained parent-EJ SIREN and compare it with each proposed SIRET."""
    reference = ej_decisions[["EJ", "Siren_retenu"]].copy()
    retained = reference["Siren_retenu"].astype("string")
    reference["Siren_retenu"] = retained.mask(retained.str.strip().str.upper().eq("NA"))
    reference = reference.dropna(subset=["EJ", "Siren_retenu"]).rename(
        columns={"Siren_retenu": "siren_reference_EJ"}
    )
    reference["EJ"] = normalize_identifier_series(reference["EJ"], 9)
    reference["siren_reference_EJ"] = normalize_identifier_series(
        reference["siren_reference_EJ"], 9
    )

    out = proposal_table.merge(
        reference,
        on="EJ",
        how="left",
        validate="many_to_one",
    )
    out["coherence_siren_du_siret_avec_siren_ej_corrige"] = (
        out["siren"]
        .eq(out["siren_reference_EJ"])
        .astype("boolean")
        .mask(
            out["siren"].isna() | out["siren_reference_EJ"].isna(),
            pd.NA,
        )
    )
    return out


def finalize_proposals(proposal_table: pd.DataFrame) -> pd.DataFrame:
    """Apply final EGE names/status labels and the stable downstream column order."""
    out = proposal_table.rename(
        columns={
            "consistency_type": "datasets_consistency_EGE",
            "dataset1__proposals": "sirets_ANS",
            "dataset2__proposals": "sirets_Adrien",
            "dataset1__proposal_count": "n_sirets_ANS",
            "dataset2__proposal_count": "n_sirets_Adrien",
            "dataset1__statut_eg": "statut_EGE_ANS",
            "dataset1__phase_eg": "phase_EGE_ANS",
            "dataset1__siret": "siret_EGE_ANS",
            "EGE__siret": "initial_siret",
            "siret__etatAdministratifEtablissement": "etat_siret",
            "siren_reference_EJ": "siren_ej_corrige",
        }
    ).copy()

    if out.columns.duplicated().any():
        duplicates = out.columns[out.columns.duplicated()].tolist()
        raise ValueError(f"Duplicate columns after final renaming: {duplicates}")

    out["etat_siret"] = out["etat_siret"].astype("string").replace(
        {"A": "", "C": "Cessé", "F": "Fermé"}
    )
    return select_and_order_columns(out, FINAL_COLUMN_ORDER)
