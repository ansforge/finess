"""Design-weighted global summaries and accepted-strata scenarios.

This module is separate from ``analyze_reviews`` so per-stratum analysis remains
focused and auditable. Global estimates start from the sampling weight already
present in the enriched strata plan and calibrate it within stratum to the known
analysis-population total. This calibration is neutral for ordinary EJ weights
(N_h / n_h) and prevents EGE two-stage design expansion from re-estimating a
population total that is already known exactly from the strata plan.
"""

from __future__ import annotations

import math
import textwrap
from collections.abc import Iterable
from pathlib import Path

import analyze_reviews as ar
import pandas as pd

GLOBAL_METRIC_COLUMNS = [
    "Metric",
    "Population count",
    "Proportion (%)",
    "Denominator",
    "Denominator population",
    "Basis",
]

SATISFACTORY_COLUMNS = [
    "Method",
    "Threshold",
    "Estimated entities to match in satisfactory strata",
    "Share of entities to match in satisfactory strata (%)",
]

ACCEPTED_STRATA_SCENARIO_COLUMNS = [
    "Scenario",
    "Threshold",
    "Estimated entities to match in accepted strata",
    "Share of entities to match in accepted strata (%)",
    "Estimated correct in accepted strata",
    "Estimated Initial-correct entities in untouched strata",
    "Estimated total correct after rule",
    "Overall correctness (%)",
    "Gain vs Initial (percentage points)",
    "Gain vs Initial (estimated entities)",
    "Estimated mistakes corrected in accepted strata",
    "Estimated mistakes introduced in accepted strata",
]


def _require_columns(df: pd.DataFrame, columns: Iterable[str], *, source: str) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ar.DataValidationError(f"{source}: missing required columns: {missing}")


def _numeric(values: pd.Series, *, source: str, allow_na: bool = False) -> pd.Series:
    converted = pd.to_numeric(values, errors="coerce")
    if not allow_na and converted.isna().any():
        bad = values.loc[converted.isna()].astype(str).head(5).tolist()
        raise ar.DataValidationError(
            f"{source}: expected numeric values; examples: {bad}"
        )
    return converted.astype(float)


def _calibrated_plan_weights(
    enriched_plan_df: pd.DataFrame,
    *,
    config: ar.ReviewAnalysisConfig,
) -> pd.Series:
    """Return stratum weights calibrated to the known analysis population.

    The enriched EGE plan stores a two-stage design expansion weight. Multiplying
    that weight by the realized reviewed count re-estimates the EGE population,
    even though the exact stratum population is already known in ``Population
    size``. For global totals and proportions we therefore apply a standard
    within-stratum calibration factor::

        g_h = N_h / (n_h * w_h)
        w_h_calibrated = w_h * g_h

    Consequently ``n_h * w_h_calibrated == N_h``. EJ design weights are already
    ``N_h / n_h``, so their calibration factor is 1 (apart from rounding).
    """

    names = config.analysis_columns
    required = (
        names["stratum_id"],
        names["population_size"],
        names["reviewed"],
        names["sampling_weight"],
    )
    _require_columns(enriched_plan_df, required, source="enriched_plan_df")

    plan = enriched_plan_df[list(required)].copy()
    duplicate = plan[names["stratum_id"]].duplicated(keep=False)
    if duplicate.any():
        strata = plan.loc[duplicate, names["stratum_id"]].astype(str).tolist()
        raise ar.DataValidationError(
            f"enriched_plan_df must contain one row per stratum; duplicates: {strata[:10]}"
        )

    population = _numeric(
        plan[names["population_size"]],
        source="enriched_plan_df[Population size]",
    )
    reviewed = _numeric(
        plan[names["reviewed"]],
        source=f"enriched_plan_df[{names['reviewed']!r}]",
        allow_na=True,
    ).fillna(0.0)
    design_weight = _numeric(
        plan[names["sampling_weight"]],
        source="enriched_plan_df[Sampling weight]",
    )

    if (population < 0).any():
        raise ar.DataValidationError("Population size must be non-negative.")
    if (design_weight <= 0).any():
        raise ar.DataValidationError("Sampling weights must be positive.")

    missing_sample = population.gt(0) & reviewed.le(0)
    if missing_sample.any():
        strata = plan.loc[missing_sample, names["stratum_id"]].astype(str).tolist()
        raise ar.DataValidationError(
            "Every non-empty stratum needs a completed review sample for global "
            f"calibration; invalid strata: {strata[:10]}"
        )

    design_expansion = reviewed * design_weight
    calibration = pd.Series(1.0, index=plan.index, dtype=float)
    nonempty = population.gt(0)
    calibration.loc[nonempty] = (
        population.loc[nonempty] / design_expansion.loc[nonempty]
    )
    calibrated = design_weight * calibration
    return calibrated.astype(float)


def _stratum_weights(
    outcomes: pd.DataFrame,
    enriched_plan_df: pd.DataFrame,
    *,
    config: ar.ReviewAnalysisConfig,
) -> pd.Series:
    """Map population-calibrated stratum weights to every reviewed entity."""

    names = config.analysis_columns
    calibrated = _calibrated_plan_weights(enriched_plan_df, config=config)
    weight_by_stratum = pd.Series(
        calibrated.values,
        index=enriched_plan_df[names["stratum_id"]].astype(str),
    )
    weights = outcomes["Stratum ID"].astype(str).map(weight_by_stratum)
    if weights.isna().any():
        missing = outcomes.loc[weights.isna(), "Stratum ID"].unique().tolist()
        raise ar.DataValidationError(
            f"Missing calibrated sampling weight for reviewed strata: {missing[:10]}"
        )
    return weights.astype(float).reset_index(drop=True)


def _weighted_sum(outcomes: pd.DataFrame, weights: pd.Series, indicator: str) -> float:
    return float(
        (outcomes[indicator].astype(float).reset_index(drop=True) * weights).sum()
    )


def _initial_population_stats(
    proposal_df: pd.DataFrame,
    enriched_plan_df: pd.DataFrame,
    *,
    config: ar.ReviewAnalysisConfig,
) -> tuple[int, int]:
    """Return the exact initial-NA count and exact proposal-table population size.

    This statistic is descriptive of the complete original proposal table and is
    deliberately not estimated from the review sample.
    """

    proposals = ar._to_internal(
        proposal_df,
        config,
        required_internal=(
            ar.ENTITY_ID,
            ar.BUSINESS_ID_PROPOSAL,
            ar.STRATUM_ID,
            ar.IS_INITIAL_PROPOSAL,
        ),
        source="proposal_df",
    )
    proposals["_entity_id_norm"] = proposals[ar.ENTITY_ID].map(ar._canonical_identifier)
    proposals["_is_initial"] = proposals[ar.IS_INITIAL_PROPOSAL].map(ar._is_true)
    if proposals["_entity_id_norm"].isna().any():
        raise ar.DataValidationError("proposal_df contains missing entity identifiers.")

    initial_counts = proposals.groupby("_entity_id_norm")["_is_initial"].sum()
    bad = initial_counts[initial_counts != 1]
    if not bad.empty:
        raise ar.DataValidationError(
            "The original proposal table must contain exactly one Initial row per entity; "
            f"invalid entities include: {bad.index.tolist()[:10]}"
        )

    initial = proposals.loc[proposals["_is_initial"]].copy()
    population_count = int(initial["_entity_id_norm"].nunique())
    initial_na_count = int(
        initial[ar.BUSINESS_ID_PROPOSAL]
        .map(ar._canonical_identifier)
        .map(lambda value: ar._business_is_na(value, config))
        .sum()
    )

    names = config.analysis_columns
    _require_columns(
        enriched_plan_df, (names["population_size"],), source="enriched_plan_df"
    )
    planned_population = round(
            _numeric(
                enriched_plan_df[names["population_size"]],
                source="enriched_plan_df[Population size]",
            ).sum()
        )
    if planned_population != population_count:
        raise ar.DataValidationError(
            "The exact Initial-NA statistic requires the proposal table to cover the "
            f"complete analysis population. Proposal entities={population_count:,}; "
            f"strata-plan population={planned_population:,}."
        )
    return initial_na_count, population_count


def _stratum_numeric(
    enriched_plan_df: pd.DataFrame,
    column: str,
    *,
    source: str | None = None,
) -> pd.Series:
    return _numeric(
        enriched_plan_df[column],
        source=source or f"enriched_plan_df[{column!r}]",
        allow_na=True,
    )


def _method_components(
    enriched_plan_df: pd.DataFrame,
    *,
    config: ar.ReviewAnalysisConfig,
) -> tuple[
    dict[str, pd.Series],
    dict[str, pd.Series],
    dict[str, pd.Series],
    dict[str, pd.Series],
]:
    """Return deployable point estimates plus joint Initial-transition counts."""

    names = config.analysis_columns
    required = [
        names["initial_correct_pct"],
        names["ans_fallback_correct_pct"],
        names["adrien_fallback_correct_pct"],
        names["adrien_only_fallback_correct_pct"],
        names["initial_correct"],
        names["ans_fallback_correct"],
        names["adrien_fallback_correct"],
        names["adrien_only_fallback_correct"],
        names["ans_fallback_mistakes_corrected"],
        names["ans_fallback_mistakes_introduced"],
        names["adrien_fallback_mistakes_corrected"],
        names["adrien_fallback_mistakes_introduced"],
        names["adrien_only_fallback_mistakes_corrected"],
        names["adrien_only_fallback_mistakes_introduced"],
    ]
    _require_columns(enriched_plan_df, required, source="enriched_plan_df")

    pcts = {
        "Initial": _stratum_numeric(enriched_plan_df, names["initial_correct_pct"]),
        "ANS + Initial fallback": _stratum_numeric(
            enriched_plan_df, names["ans_fallback_correct_pct"]
        ),
        "Adrien + Initial fallback": _stratum_numeric(
            enriched_plan_df, names["adrien_fallback_correct_pct"]
        ),
        "Adrien — only proposal + Initial fallback": _stratum_numeric(
            enriched_plan_df, names["adrien_only_fallback_correct_pct"]
        ),
    }
    correct_counts = {
        "Initial": _stratum_numeric(enriched_plan_df, names["initial_correct"]),
        "ANS + Initial fallback": _stratum_numeric(
            enriched_plan_df, names["ans_fallback_correct"]
        ),
        "Adrien + Initial fallback": _stratum_numeric(
            enriched_plan_df, names["adrien_fallback_correct"]
        ),
        "Adrien — only proposal + Initial fallback": _stratum_numeric(
            enriched_plan_df, names["adrien_only_fallback_correct"]
        ),
    }

    zero = pd.Series(0.0, index=enriched_plan_df.index, dtype=float)
    mistakes_corrected = {
        "Initial": zero.copy(),
        "ANS + Initial fallback": _stratum_numeric(
            enriched_plan_df, names["ans_fallback_mistakes_corrected"]
        ),
        "Adrien + Initial fallback": _stratum_numeric(
            enriched_plan_df, names["adrien_fallback_mistakes_corrected"]
        ),
        "Adrien — only proposal + Initial fallback": _stratum_numeric(
            enriched_plan_df, names["adrien_only_fallback_mistakes_corrected"]
        ),
    }
    mistakes_introduced = {
        "Initial": zero.copy(),
        "ANS + Initial fallback": _stratum_numeric(
            enriched_plan_df, names["ans_fallback_mistakes_introduced"]
        ),
        "Adrien + Initial fallback": _stratum_numeric(
            enriched_plan_df, names["adrien_fallback_mistakes_introduced"]
        ),
        "Adrien — only proposal + Initial fallback": _stratum_numeric(
            enriched_plan_df, names["adrien_only_fallback_mistakes_introduced"]
        ),
    }
    return pcts, correct_counts, mistakes_corrected, mistakes_introduced


METHOD_DEFINITIONS: dict[str, tuple[str, ...]] = {
    "Initial": ("Initial",),
    "ANS + Initial fallback": ("ANS + Initial fallback",),
    "Adrien + Initial fallback": ("Adrien + Initial fallback",),
    "Adrien — only proposal + Initial fallback": (
        "Adrien — only proposal + Initial fallback",
    ),
    "max(Initial, ANS + Initial fallback)": (
        "Initial",
        "ANS + Initial fallback",
    ),
    "max(ANS + Initial fallback, Adrien — only proposal + Initial fallback)": (
        "ANS + Initial fallback",
        "Adrien + Initial fallback",
        "Adrien — only proposal + Initial fallback",
    ),
    "max(Initial, ANS + Initial fallback, Adrien — only proposal + Initial fallback)": (
        "Initial",
        "ANS + Initial fallback",
        "Adrien + Initial fallback",
        "Adrien — only proposal + Initial fallback",
    ),
    "max(Initial, ANS + Initial fallback, Adrien + Initial fallback)": (
        "Initial",
        "ANS + Initial fallback",
        "Adrien + Initial fallback",
        "Adrien — only proposal + Initial fallback",
    ),
}


def _method_best_pct(
    method: str,
    pcts: dict[str, pd.Series],
) -> pd.Series:
    components = METHOD_DEFINITIONS[method]
    return pd.concat([pcts[name] for name in components], axis=1).max(axis=1, skipna=True)


def _method_selected_component(
    method: str,
    pcts: dict[str, pd.Series],
) -> pd.Series:
    """Select the deployable component used by a scenario in every stratum."""

    components = METHOD_DEFINITIONS[method]
    if len(components) == 1:
        return pd.Series(components[0], index=pcts[components[0]].index)

    pct_frame = pd.concat([pcts[name] for name in components], axis=1)
    pct_frame.columns = list(components)
    has_percentage = pct_frame.notna().any(axis=1)
    selected = pd.Series(pd.NA, index=pct_frame.index, dtype="object")
    # Deterministic first-component tie breaking is intentional and is shared by
    # correctness, corrected-mistake and introduced-mistake accounting.
    selected.loc[has_percentage] = pct_frame.loc[has_percentage].idxmax(
        axis=1, skipna=True
    )
    return selected


def _method_selected_metric(
    method: str,
    pcts: dict[str, pd.Series],
    metrics: dict[str, pd.Series],
) -> pd.Series:
    """Return the per-stratum metric for the component selected by ``method``."""

    selected = _method_selected_component(method, pcts)
    result = pd.Series(0.0, index=selected.index, dtype=float)
    for name in METHOD_DEFINITIONS[method]:
        mask = selected.eq(name).fillna(False)
        result.loc[mask] = metrics[name].loc[mask].fillna(0.0)
    return result


def _matchable_stratum_population(
    enriched_plan_df: pd.DataFrame,
    *,
    config: ar.ReviewAnalysisConfig,
) -> tuple[pd.Series, pd.Series, float]:
    names = config.analysis_columns
    _require_columns(
        enriched_plan_df,
        (names["to_match"],),
        source="enriched_plan_df",
    )
    to_match = _stratum_numeric(enriched_plan_df, names["to_match"]).fillna(0.0)
    weights = _calibrated_plan_weights(enriched_plan_df, config=config)
    matchable = to_match * weights
    return matchable, weights, float(matchable.sum())


def summarize_accepted_strata_scenarios(
    enriched_plan_df: pd.DataFrame,
    *,
    config: ar.ReviewAnalysisConfig = ar.EJ_SIREN_CONFIG,
) -> pd.DataFrame:
    """Estimate outcomes under 95% / 99% accepted-strata rules.

    A stratum is accepted when the scenario's deployable rule reaches the
    threshold. For ANS and Adrien rules, deployment is entity-level: use the
    method when it has a proposal and otherwise retain Initial. For the Adrien
    one-proposal rule, use Adrien only when that rule is applicable and otherwise
    retain Initial. Every non-accepted stratum remains entirely on Initial.
    Combined scenarios select the deployable rule with the highest observed
    stratum point estimate among the rules named in the scenario.
    """

    matchable, weights, total_matchable = _matchable_stratum_population(
        enriched_plan_df, config=config
    )
    pcts, counts, mistakes_corrected, mistakes_introduced = _method_components(
        enriched_plan_df, config=config
    )
    initial_correct_weighted = counts["Initial"].fillna(0.0) * weights
    baseline_correct = float(initial_correct_weighted.sum())
    baseline_pct = (
        pd.NA
        if total_matchable <= 0
        else round(100 * baseline_correct / total_matchable, 2)
    )

    rows: list[dict[str, object]] = []

    scenario_methods = list(METHOD_DEFINITIONS)
    for method in scenario_methods:
        best_pct = _method_best_pct(method, pcts)
        selected_correct_counts = _method_selected_metric(method, pcts, counts)
        selected_mistakes_corrected = _method_selected_metric(
            method, pcts, mistakes_corrected
        )
        selected_mistakes_introduced = _method_selected_metric(
            method, pcts, mistakes_introduced
        )
        selected_correct_weighted = selected_correct_counts * weights
        selected_mistakes_corrected_weighted = selected_mistakes_corrected * weights
        selected_mistakes_introduced_weighted = selected_mistakes_introduced * weights

        for threshold in (95.0, 99.0):
            accepted = best_pct.ge(threshold).fillna(False)
            accepted_population = float(matchable.loc[accepted].sum())
            correct_accepted = float(selected_correct_weighted.loc[accepted].sum())
            mistakes_corrected_accepted = float(
                selected_mistakes_corrected_weighted.loc[accepted].sum()
            )
            mistakes_introduced_accepted = float(
                selected_mistakes_introduced_weighted.loc[accepted].sum()
            )
            correct_untouched = float(initial_correct_weighted.loc[~accepted].sum())
            total_correct = correct_accepted + correct_untouched
            overall_pct = (
                pd.NA
                if total_matchable <= 0
                else round(100 * total_correct / total_matchable, 2)
            )
            gain_pp = (
                pd.NA
                if pd.isna(overall_pct) or pd.isna(baseline_pct)
                else round(float(overall_pct) - float(baseline_pct), 2)
            )

            # Joint-transition accounting must reproduce the net correctness gain.
            transition_net_gain = mistakes_corrected_accepted - mistakes_introduced_accepted
            total_net_gain = total_correct - baseline_correct
            if not math.isclose(transition_net_gain, total_net_gain, abs_tol=1e-8):
                raise ar.DataValidationError(
                    "Accepted-strata transition accounting is inconsistent with the "
                    f"net gain for scenario {method!r} at {threshold:.0f}%."
                )

            rows.append(
                {
                    "Scenario": method,
                    "Threshold": f"{int(threshold)}%",
                    "Estimated entities to match in accepted strata": round(
                        accepted_population, 2
                    ),
                    "Share of entities to match in accepted strata (%)": (
                        pd.NA
                        if total_matchable <= 0
                        else round(100 * accepted_population / total_matchable, 2)
                    ),
                    "Estimated correct in accepted strata": round(correct_accepted, 2),
                    "Estimated Initial-correct entities in untouched strata": round(
                        correct_untouched, 2
                    ),
                    "Estimated total correct after rule": round(total_correct, 2),
                    "Overall correctness (%)": overall_pct,
                    "Gain vs Initial (percentage points)": gain_pp,
                    "Gain vs Initial (estimated entities)": round(
                        total_correct - baseline_correct, 2
                    ),
                    "Estimated mistakes corrected in accepted strata": round(
                        mistakes_corrected_accepted, 2
                    ),
                    "Estimated mistakes introduced in accepted strata": round(
                        mistakes_introduced_accepted, 2
                    ),
                }
            )

    return pd.DataFrame(rows, columns=ACCEPTED_STRATA_SCENARIO_COLUMNS)


def summarize_global_reviews(
    confirmed_decisions_df: pd.DataFrame,
    proposal_df: pd.DataFrame,
    enriched_plan_df: pd.DataFrame,
    *,
    config: ar.ReviewAnalysisConfig = ar.EJ_SIREN_CONFIG,
) -> dict[str, pd.DataFrame]:
    """Compute global review metrics and deployable accepted-strata scenarios."""

    outcomes = ar.build_entity_review_outcomes(
        confirmed_decisions_df, proposal_df, config=config
    )
    weights = _stratum_weights(outcomes, enriched_plan_df, config=config)

    reviewed_population = _weighted_sum(outcomes, weights, "reviewed")
    matchable_population = _weighted_sum(outcomes, weights, "to_match")
    ans_available_population = _weighted_sum(outcomes, weights, "ans_proposed")
    adrien_available_population = _weighted_sum(outcomes, weights, "adrien_proposed")
    adrien_only_available_population = _weighted_sum(
        outcomes, weights, "adrien_only_proposed"
    )
    initial_na_exact, original_population_exact = _initial_population_stats(
        proposal_df, enriched_plan_df, config=config
    )

    e = config.entity_plural
    b = config.business_upper
    denominator_specs = {
        "match": (matchable_population, f"{e} to match"),
        "reviewed": (reviewed_population, f"{e} examined"),
        "ans_available": (
            ans_available_population,
            f"{e} to match with an ANS proposal",
        ),
        "adrien_available": (
            adrien_available_population,
            f"{e} to match with an Adrien proposal",
        ),
        "adrien_only_available": (
            adrien_only_available_population,
            f"{e} to match where Adrien has one proposal",
        ),
    }

    weighted_specs = [
        ("Initial correct", "initial_correct", "match", "Calibrated design-weighted estimate"),
        ("ANS coverage", "ans_proposed", "match", "Calibrated design-weighted estimate"),
        (
            "ANS correct when proposed",
            "ans_correct",
            "ans_available",
            "Calibrated design-weighted estimate",
        ),
        (
            "ANS + Initial fallback correct",
            "ans_fallback_correct",
            "match",
            "Deployable rule: use ANS when available, otherwise retain Initial",
        ),
        (
            "Adrien coverage",
            "adrien_proposed",
            "match",
            "Calibrated design-weighted estimate",
        ),
        (
            "Adrien correct when proposed",
            "adrien_correct",
            "adrien_available",
            "Calibrated design-weighted estimate",
        ),
        (
            "Adrien + Initial fallback correct",
            "adrien_fallback_correct",
            "match",
            "Deployable rule: use Adrien when available, otherwise retain Initial",
        ),
        (
            "Adrien — only proposal coverage",
            "adrien_only_proposed",
            "match",
            "Calibrated design-weighted estimate",
        ),
        (
            "Adrien correct — only proposal, when applicable",
            "adrien_only_correct",
            "adrien_only_available",
            "Calibrated design-weighted estimate",
        ),
        (
            "Adrien — only proposal + Initial fallback correct",
            "adrien_only_fallback_correct",
            "match",
            "Deployable rule: use Adrien when the one-proposal rule applies, otherwise retain Initial",
        ),
        (
            "Neither ANS nor Adrien correct",
            "neither_correct",
            "match",
            "Calibrated design-weighted estimate",
        ),
        (
            f"Initial correct — estimated among all {e}",
            "initial_correct",
            "reviewed",
            "Calibrated design-weighted estimate",
        ),
        (
            f"{e} with uncertainty",
            "with_uncertainty",
            "reviewed",
            "Calibrated design-weighted estimate",
        ),
        (
            f"{e} to close",
            "to_close",
            "reviewed",
            "Calibrated design-weighted estimate",
        ),
        (
            f"{e} with {b} identified",
            "business_identified",
            "match",
            "Calibrated design-weighted estimate",
        ),
    ]

    rows: list[dict[str, object]] = []
    for label, indicator, denominator_kind, basis in weighted_specs:
        estimate = _weighted_sum(outcomes, weights, indicator)
        denominator, denominator_label = denominator_specs[denominator_kind]
        rows.append(
            {
                "Metric": label,
                "Population count": round(estimate, 2),
                "Proportion (%)": (
                    pd.NA
                    if denominator <= 0
                    else round(100 * estimate / denominator, 2)
                ),
                "Denominator": denominator_label,
                "Denominator population": round(denominator, 2),
                "Basis": basis,
            }
        )

    # Put the exact Initial-NA row next to the full-population Initial-correct row.
    exact_row = {
        "Metric": f"Initial NA — among all {e}",
        "Population count": initial_na_exact,
        "Proportion (%)": (
            pd.NA
            if original_population_exact <= 0
            else round(100 * initial_na_exact / original_population_exact, 2)
        ),
        "Denominator": f"All {e} in original proposal table",
        "Denominator population": original_population_exact,
        "Basis": "Observed directly from original proposal table",
    }
    insertion_index = next(
        (
            idx + 1
            for idx, row in enumerate(rows)
            if row["Metric"] == f"Initial correct — estimated among all {e}"
        ),
        len(rows),
    )
    rows.insert(insertion_index, exact_row)

    global_summary_df = pd.DataFrame(rows, columns=GLOBAL_METRIC_COLUMNS)
    scenarios_df = summarize_accepted_strata_scenarios(
        enriched_plan_df, config=config
    )
    return {
        "global_summary_df": global_summary_df,
        "accepted_strata_scenarios_df": scenarios_df,
    }


def validate_global_analysis_consistency(
    proposal_df: pd.DataFrame,
    plan_df: pd.DataFrame,
    global_summary_df: pd.DataFrame,
    accepted_strata_scenarios_df: pd.DataFrame,
    *,
    config: ar.ReviewAnalysisConfig = ar.EJ_SIREN_CONFIG,
) -> dict[str, float]:
    """Validate global accounting and known-population identities.

    These checks protect the interface between per-stratum analysis and global
    reporting. They are explicit runtime validations rather than ``assert``
    statements so they remain active in every Python execution mode.
    """
    population_column = config.effective_population_size_column
    _require_columns(
        plan_df,
        (config.stratum_id_column, population_column),
        source="plan_df",
    )
    _require_columns(
        proposal_df,
        (config.entity_id_column,),
        source="proposal_df",
    )
    _require_columns(
        global_summary_df,
        GLOBAL_METRIC_COLUMNS,
        source="global_summary_df",
    )
    _require_columns(
        accepted_strata_scenarios_df,
        (
            "Estimated mistakes corrected in accepted strata",
            "Estimated mistakes introduced in accepted strata",
            "Gain vs Initial (estimated entities)",
        ),
        source="accepted_strata_scenarios_df",
    )

    transition_gain = _numeric(
        accepted_strata_scenarios_df[
            "Estimated mistakes corrected in accepted strata"
        ],
        source="accepted_strata_scenarios_df[corrected mistakes]",
    ) - _numeric(
        accepted_strata_scenarios_df[
            "Estimated mistakes introduced in accepted strata"
        ],
        source="accepted_strata_scenarios_df[introduced mistakes]",
    )
    reported_gain = _numeric(
        accepted_strata_scenarios_df["Gain vs Initial (estimated entities)"],
        source="accepted_strata_scenarios_df[reported gain]",
    )
    if ((transition_gain - reported_gain).abs() >= 0.02).any():
        raise ar.DataValidationError(
            "Corrected-minus-introduced transition accounting does not reproduce "
            "the reported net gain."
        )

    known_population = float(
        pd.to_numeric(plan_df[population_column], errors="raise").sum()
    )
    proposal_population = float(
        proposal_df[config.entity_id_column]
        .astype("string")
        .str.strip()
        .replace("", pd.NA)
        .dropna()
        .nunique()
    )

    examined_label = f"{config.entity_plural} examined"
    examined_denominators = (
        pd.to_numeric(
            global_summary_df.loc[
                global_summary_df["Denominator"].eq(examined_label),
                "Denominator population",
            ],
            errors="coerce",
        )
        .dropna()
        .unique()
    )
    if len(examined_denominators) != 1:
        raise ar.DataValidationError(
            f"Expected one common global {examined_label!r} denominator."
        )
    examined_population = float(examined_denominators[0])

    initial_rows = global_summary_df.loc[
        global_summary_df["Metric"].eq("Initial correct"),
        "Denominator population",
    ]
    if len(initial_rows) != 1:
        raise ar.DataValidationError(
            "global_summary_df must contain exactly one 'Initial correct' row."
        )
    match_population = float(pd.to_numeric(initial_rows, errors="raise").iloc[0])

    close_label = f"{config.entity_plural} to close"
    close_rows = global_summary_df.loc[
        global_summary_df["Metric"].eq(close_label),
        "Population count",
    ]
    if len(close_rows) != 1:
        raise ar.DataValidationError(
            f"global_summary_df must contain exactly one {close_label!r} row."
        )
    close_population = float(pd.to_numeric(close_rows, errors="raise").iloc[0])

    if abs(proposal_population - known_population) >= 0.01:
        raise ar.DataValidationError(
            f"Proposal population ({proposal_population:,.2f}) does not match the "
            f"strata-plan population ({known_population:,.2f})."
        )
    if abs(examined_population - known_population) >= 0.01:
        raise ar.DataValidationError(
            f"Calibrated examined denominator ({examined_population:,.2f}) does not "
            f"match the known population ({known_population:,.2f})."
        )
    if abs((match_population + close_population) - known_population) >= 0.02:
        raise ar.DataValidationError(
            f"Estimated to-match + to-close "
            f"({match_population + close_population:,.2f}) does not match the known "
            f"population ({known_population:,.2f})."
        )

    return {
        "known_population": known_population,
        "proposal_population": proposal_population,
        "examined_population": examined_population,
        "match_population": match_population,
        "close_population": close_population,
    }


def _methodological_note_row_height(note: str, worksheet) -> float:
    """Estimate an Excel row height that fits the wrapped methodological note."""

    column_width = worksheet.column_dimensions["A"].width or 12
    # Excel's width unit is approximately one character for ordinary text. Leave
    # a little safety margin because proportional fonts and cell padding vary.
    chars_per_line = max(12, int(column_width * 0.9))

    line_count = 0
    for paragraph in str(note).splitlines() or [""]:
        wrapped = textwrap.wrap(
            paragraph,
            width=chars_per_line,
            break_long_words=False,
            break_on_hyphens=False,
        )
        line_count += max(1, len(wrapped))

    # Excel row heights are points; cap just below Excel's practical maximum.
    return min(409.0, max(30.0, 6.0 + 15.0 * line_count))


def export_global_summary(
    summaries: dict[str, pd.DataFrame],
    output_path: str | Path,
    *,
    note: str | None = None,
) -> None:
    """Export the two global-reporting sheets to one Excel workbook.

    The optional note is written below the Sheet 1 statistics rather than above
    them, so the table remains immediately visible when the workbook is opened.
    """

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    global_df, global_formats = ar._prepare_dataframe_for_excel(
        summaries["global_summary_df"]
    )
    scenarios_df, scenario_formats = ar._prepare_dataframe_for_excel(
        summaries["accepted_strata_scenarios_df"]
    )

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        global_df.to_excel(
            writer,
            index=False,
            sheet_name="global_review_summary",
            na_rep="",
        )
        scenarios_df.to_excel(
            writer,
            index=False,
            sheet_name="accepted_strata_scenarios",
            na_rep="",
        )

        ar._format_excel_worksheet(
            writer.sheets["global_review_summary"],
            global_df,
            global_formats,
            table_end_row=1 + len(global_df),
        )
        ar._format_excel_worksheet(
            writer.sheets["accepted_strata_scenarios"],
            scenarios_df,
            scenario_formats,
            table_end_row=1 + len(scenarios_df),
        )

        if note:
            note_row = len(global_df) + 3
            pd.DataFrame({"Methodological note": [note]}).to_excel(
                writer,
                index=False,
                sheet_name="global_review_summary",
                startrow=note_row,
            )
            worksheet = writer.sheets["global_review_summary"]
            note_header_row = note_row + 1
            note_text_row = note_row + 2
            from openpyxl.styles import Alignment, Font

            worksheet.cell(note_header_row, 1).font = Font(bold=True)
            worksheet.cell(note_header_row, 1).alignment = Alignment(wrap_text=True)
            worksheet.cell(note_text_row, 1).alignment = Alignment(
                vertical="top", wrap_text=True
            )
            worksheet.row_dimensions[note_text_row].height = (
                _methodological_note_row_height(note, worksheet)
            )
