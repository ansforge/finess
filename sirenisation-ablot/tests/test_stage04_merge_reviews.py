from __future__ import annotations

import merge_reviews
import pandas as pd
import pytest


def _review_row(stratum_id, entity, reviewed, source_file):
    return {
        "EJ": entity,
        "stratum_id": stratum_id,
        "Siren_retenu": "123456789" if reviewed else "",
        "Incertitude1": "0" if reviewed else "",
        "Commentaire": "",
        "_source_file": source_file,
    }


def test_additional_decisions_keep_current_review_on_overlap():
    current = pd.DataFrame(
        {
            "EJ": ["1", "2"],
            "Siren_retenu": ["111111111", "222222222"],
            "Incertitude1": ["0", "1"],
            "Commentaire": ["", "current"],
        }
    )
    additional = pd.DataFrame(
        {
            "EJ": ["1", "2", "3"],
            "Siren_retenu": ["111111111", "999999999", "333333333"],
            "Incertitude1": ["0", "0", "0"],
            "Commentaire": ["", "different", "new"],
        }
    )

    result = merge_reviews.combine_confirmed_decision_sets(
        current,
        additional,
        config=merge_reviews.EJ_SIREN_CONFIG,
    )

    assert result.identical_overlaps == ["1"]
    assert result.conflicting_overlaps == ["2"]
    assert result.additional_only_entities == ["3"]
    kept = result.combined_decisions.set_index("EJ").loc["2"]
    assert kept["Siren_retenu"] == "222222222"
    assert kept["Commentaire"] == "current"


def test_additional_ege_must_belong_to_pooled_frame():
    additional = pd.DataFrame(
        {
            "EGE": ["1", "3"],
            "Siret_retenu": ["11111111111111", "33333333333333"],
            "Incertitude1": ["0", "0"],
            "Commentaire": ["", ""],
        }
    )
    validated = merge_reviews.validate_confirmed_decision_table(
        additional,
        config=merge_reviews.EGE_SIRET_CONFIG,
        source="additional.xlsx",
    )

    with pytest.raises(merge_reviews.DataValidationError, match="reference frame"):
        merge_reviews.validate_confirmed_entities_in_reference(
            validated,
            pd.DataFrame({"EGE": ["1", "2"]}),
            config=merge_reviews.EGE_SIRET_CONFIG,
            source="additional.xlsx",
        )


def test_review_design_reports_shortfall_and_gap_but_keeps_extension_silent(capsys):
    plan = pd.DataFrame(
        {
            "stratum_id": ["000001", "000002", "000003"],
            "reviewer": ["alice", "bob", "carol"],
            "sample_size": [3, 2, 3],
        }
    )
    rows = [
        _review_row("000001", "A1", True, "000001__3.xlsx"),
        _review_row("000001", "A2", True, "000001__3.xlsx"),
        _review_row("000001", "A3", False, "000001__3.xlsx"),
        _review_row("000002", "B1", True, "000002__2.xlsx"),
        _review_row("000002", "B2", True, "000002__2.xlsx"),
        _review_row("000002", "B3", True, "000002__2.xlsx"),
        _review_row("000003", "C1", True, "000003__3.xlsx"),
        _review_row("000003", "C2", False, "000003__3.xlsx"),
        _review_row("000003", "C3", True, "000003__3.xlsx"),
        _review_row("000003", "C4", False, "000003__3.xlsx"),
    ]

    diagnostics = merge_reviews.report_review_design_deviations(
        plan_df=plan,
        stratum_df=pd.DataFrame(rows),
        config=merge_reviews.EJ_SIREN_CONFIG,
    )
    output = capsys.readouterr().out

    assert [(x["stratum_id"], x["reviewed_entities"]) for x in diagnostics["review_shortfalls"]] == [
        ("000001", 2),
        ("000003", 2),
    ]
    assert [(x["stratum_id"], x["reviewed_entities"]) for x in diagnostics["review_extensions"]] == [
        ("000002", 3)
    ]
    assert diagnostics["internal_review_gaps"][0]["unreviewed_gap_entities"] == ["C2"]
    assert "Review sample shortfalls" in output
    assert "unreviewed EJ(s) within the reviewed prefix: C2" in output
    assert "extensions beyond" not in output.lower()


def test_multiple_candidate_rows_do_not_create_false_internal_gaps():
    plan = pd.DataFrame(
        {"stratum_id": ["000001"], "reviewer": ["alice"], "sample_size": [2]}
    )
    rows = [
        _review_row("000001", "A1", True, "000001__2.xlsx"),
        _review_row("000001", "A1", False, "000001__2.xlsx"),
        _review_row("000001", "A2", True, "000001__2.xlsx"),
        _review_row("000001", "A2", False, "000001__2.xlsx"),
        _review_row("000001", "A3", False, "000001__2.xlsx"),
    ]

    diagnostics = merge_reviews.report_review_design_deviations(
        plan_df=plan,
        stratum_df=pd.DataFrame(rows),
        config=merge_reviews.EJ_SIREN_CONFIG,
    )

    assert diagnostics["review_shortfalls"] == []
    assert diagnostics["review_extensions"] == []
    assert diagnostics["internal_review_gaps"] == []


def test_invalid_workbook_writes_actionable_correction_report(tmp_path):
    review_root = tmp_path / "reviewed"
    reviewer_dir = review_root / "alice"
    reviewer_dir.mkdir(parents=True)

    pd.DataFrame(
        {
            "EJ": ["000000001", "000000001"],
            "stratum_id": ["000001", "000001"],
            "Siren_retenu": ["111111111", "222222222"],
            "Incertitude1": ["0", "0"],
            "Commentaire": ["", ""],
        }
    ).to_excel(reviewer_dir / "000001__1.xlsx", index=False)

    correction_report = tmp_path / "corrections.csv"
    with pytest.raises(merge_reviews.DataValidationError):
        merge_reviews.load_stratum_files(
            review_root,
            config=merge_reviews.EJ_SIREN_CONFIG,
            correction_report_path=correction_report,
        )

    corrections = pd.read_csv(correction_report)
    assert not corrections.empty
    assert corrections["blocking_reason"].astype(str).str.contains(
        "multiple distinct values"
    ).any()


def test_entity_cannot_appear_in_multiple_review_workbooks(tmp_path):
    review_root = tmp_path / "reviewed"
    for reviewer in ("alice", "bob"):
        folder = review_root / reviewer
        folder.mkdir(parents=True)
        pd.DataFrame(
            {
                "EJ": ["000000001"],
                "stratum_id": ["000001"],
                "Siren_retenu": ["111111111"],
                "Incertitude1": ["0"],
                "Commentaire": [""],
            }
        ).to_excel(folder / "000001__1.xlsx", index=False)

    with pytest.raises(merge_reviews.DataValidationError, match="blocking issue"):
        merge_reviews.load_stratum_files(
            review_root,
            config=merge_reviews.EJ_SIREN_CONFIG,
        )
