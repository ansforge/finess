"""Build the pooled EGE proposal frame used for Stage 02 review planning.

This job keeps Stage 01 EGE proposal rows whose parent EJ has a confirmed
Stage 04 decision. The resulting pooled EGE frame defines the EGE population
available for second-stage sampling and is consumed by the EGE strata-plan,
sample-size and review-analysis jobs.
"""

from __future__ import annotations


def run() -> None:
    import re

    import pandas as pd

    from project_config import PATHS

    # ----------------------------
    # Configuration
    # ----------------------------
    EGE_PROPOSALS_PATH = PATHS.stage01_ege_proposals
    POOLED_EGE_PATH = PATHS.stage02_ege_pooled_proposals

    # Use the final EJ decision set when the optional additional-decisions
    # job has been run; otherwise use the current review consolidation.
    EJ_DECISIONS_PATH = (
        PATHS.stage04_ej_all_confirmed
        if PATHS.stage04_ej_all_confirmed.exists()
        else PATHS.stage04_ej_confirmed
    )

    def normalize_identifier(value, width: int | None = None) -> str:
        """Normalize identifiers for matching without changing displayed values."""
        if pd.isna(value):
            return ""

        s = str(value).strip()
        if re.fullmatch(r"\d+\.0", s):
            s = s[:-2]
        if width is not None and s.isdigit():
            s = s.zfill(width)
        return s


    def filter_to_ejs_with_confirmed_decisions(
        ege_proposals: pd.DataFrame,
        confirmed_ejs: pd.DataFrame,
    ) -> pd.DataFrame:
        """Keep EGE proposal rows whose parent EJ has a confirmed decision."""
        if "EJ" not in ege_proposals.columns:
            raise ValueError("ege_proposals must contain an 'EJ' column.")
        if "EJ" not in confirmed_ejs.columns:
            raise ValueError("examined_ejs must contain an 'EJ' column.")

        confirmed_keys = {
            normalize_identifier(value, width=9)
            for value in confirmed_ejs["EJ"]
            if normalize_identifier(value, width=9)
        }

        out = ege_proposals.copy()
        out["_ej_match_key"] = out["EJ"].map(
            lambda value: normalize_identifier(value, width=9)
        )
        out = out[out["_ej_match_key"].isin(confirmed_keys)].copy()
        return out.drop(columns="_ej_match_key")

    # ----------------------------
    # Load inputs
    # ----------------------------
    ege_proposals = pd.read_parquet(EGE_PROPOSALS_PATH)
    confirmed_ejs = pd.read_parquet(EJ_DECISIONS_PATH, columns=["EJ"])

    pooled_ege_proposals = filter_to_ejs_with_confirmed_decisions(
        ege_proposals=ege_proposals,
        confirmed_ejs=confirmed_ejs,
    )

    # ----------------------------
    # Diagnostics
    # ----------------------------
    total_rows = len(ege_proposals)
    pooled_rows = len(pooled_ege_proposals)
    total_eges = ege_proposals["EGE"].nunique(dropna=True)
    pooled_eges = pooled_ege_proposals["EGE"].nunique(dropna=True)
    confirmed_ej_keys = confirmed_ejs["EJ"].map(
        lambda value: normalize_identifier(value, width=9)
    )
    confirmed_ej_count = confirmed_ej_keys[confirmed_ej_keys.ne("")].nunique()

    print("Pooled EGE frame")
    print(f"- EJ with confirmed decisions: {confirmed_ej_count:,}")
    print(f"- EGE in Stage 01: {total_eges:,}")
    print(f"- pooled EGE: {pooled_eges:,}")
    print(f"- proposal rows retained: {pooled_rows:,} / {total_rows:,}")

    # ----------------------------
    # Export pooled review frame
    # ----------------------------
    POOLED_EGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    pooled_ege_proposals.to_parquet(POOLED_EGE_PATH, index=False)

    print(f"- saved: {POOLED_EGE_PATH.resolve()}")


if __name__ == "__main__":
    run()
