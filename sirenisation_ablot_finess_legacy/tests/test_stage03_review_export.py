from __future__ import annotations

import finess_sirene_review_export_engine as review_export
import pandas as pd
import pytest


def test_sampling_uses_entity_order_and_keeps_all_candidate_rows(ej_review_inputs):
    proposals, plan, config = ej_review_inputs

    sampled, review_count = review_export.sample_first_unique_entities_by_stratum(
        proposals,
        plan,
        config,
        display_total=1,
    )

    assert review_count == 1
    assert set(sampled["EJ"]) == {"000000002"}
    assert len(sampled) == 2


def test_export_summary_distinguishes_target_context_and_prefill(
    tmp_path, ej_review_inputs
):
    proposals, plan, config = ej_review_inputs
    config = review_export.ReviewPipelineConfig(
        **{**config.__dict__, "display_total": 2}
    )
    previous = pd.DataFrame(
        {
            "EJ": ["000000001", "000000002"],
            "Siren_retenu": ["111111111", "333333333"],
            "Incertitude1": ["0", "0"],
            "Commentaire": ["outside current review target", "current target"],
        }
    )

    results = review_export.export_review_files(
        proposals,
        plan,
        tmp_path / "review_files",
        config,
        confirmed_decisions=previous,
    )
    summary = review_export.summarize_review_export(
        results,
        plan,
        config,
        confirmed_decisions=previous,
    )

    assert summary["planned_review_entity_count"] == 1
    assert summary["exported_entity_count"] == 2
    assert summary["prefilled_entity_count"] == 2

    table = results["tester"]["000001"]
    target_rows = table.loc[table["EJ"].eq("000000002")]
    assert target_rows.iloc[0]["Siren_retenu"] == "333333333"
    if len(target_rows) > 1:
        assert target_rows.iloc[1:]["Siren_retenu"].isna().all()


def test_export_replaces_previous_batch(tmp_path, ej_review_inputs):
    proposals, plan, config = ej_review_inputs
    output_root = tmp_path / "review_files"
    stale_dir = output_root / "old_reviewer"
    stale_dir.mkdir(parents=True)
    stale_file = stale_dir / "stale.xlsx"
    stale_file.write_text("stale", encoding="utf-8")

    review_export.export_review_files(proposals, plan, output_root, config)

    assert not stale_file.exists()
    assert not stale_dir.exists()
    assert (output_root / "tester" / "000001__1.xlsx").is_file()


def test_invalid_sample_size_is_not_silently_repaired(tmp_path, ej_review_inputs):
    proposals, plan, config = ej_review_inputs
    invalid_plan = plan.copy()
    invalid_plan["sample_size"] = "-1"

    with pytest.raises(ValueError, match="non-negative integers"):
        review_export.export_review_files(
            proposals,
            invalid_plan,
            tmp_path / "review_files",
            config,
        )
