def test_compare_outcomes_classifies_improvements_and_worsenings(comparison_result) -> None:
    comparison = comparison_result

    assert comparison.improved == ("improves",)
    assert comparison.worsened == ("worsens",)
    assert set(comparison.unchanged) == {"both-correct", "same-failure"}
    assert comparison.changed == ("changed",)
    assert comparison.baseline_metrics.total == 5
    assert comparison.candidate_metrics.total == 5
    assert "category_accuracy" in comparison.deltas()


def test_compare_outcomes_serializes_metrics_and_case_groups(comparison_result) -> None:
    payload = comparison_result.as_dict()

    assert payload["baseline"]["backend"] == "baseline"
    assert payload["candidate"]["backend"] == "candidate"
    assert payload["cases"]["improved"] == ["improves"]
    assert payload["cases"]["worsened"] == ["worsens"]
    assert payload["deltas"]["category_accuracy"] == 0.0
    detail = payload["cases"]["detail"]["improves"]
    assert detail["expected"]["category"] == "bug"
    assert detail["baseline"]["actual"]["category"] == "feature"
    assert detail["candidate"]["actual"]["category"] == "bug"
    assert detail["candidate"]["mismatches"] == []
