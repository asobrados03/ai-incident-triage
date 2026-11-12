from backend.analyzers.core import FakeAnalyzer
from backend.api.schemas import IncidentCreate, TriageResult
from evaluation.runner import (
    EvaluationCase,
    evaluate,
    evaluate_cases,
    load_dataset,
    metrics_from_outcomes,
)


def test_fake_evaluation_is_reproducible_and_bounded() -> None:
    cases = load_dataset()
    first = evaluate(FakeAnalyzer(), cases)
    second = evaluate(FakeAnalyzer(), cases)

    for metrics in (first, second):
        assert metrics.total == 28
        assert metrics.valid_responses == 28
        assert metrics.errors == 0
        assert metrics.error_rate == 0
        assert metrics.latency_ms_total >= 0
        assert metrics.latency_ms_average >= 0
        assert metrics.latency_ms_p50 >= 0
        assert metrics.latency_ms_p95 >= metrics.latency_ms_p50
        for accuracy in (
            metrics.category_accuracy,
            metrics.severity_accuracy,
            metrics.priority_accuracy,
            metrics.missing_information_accuracy,
            metrics.confidence_accuracy,
            metrics.category_macro_f1,
            metrics.severity_macro_f1,
            metrics.priority_macro_f1,
            metrics.missing_information_precision,
            metrics.missing_information_recall,
            metrics.missing_information_f1,
        ):
            assert 0 <= accuracy <= 1

    assert first.category_accuracy == second.category_accuracy
    assert first.severity_accuracy == second.severity_accuracy
    assert first.priority_accuracy == second.priority_accuracy
    assert first.confusion_matrix == second.confusion_matrix


def test_evaluation_exposes_per_class_metrics_and_confusion_matrix() -> None:
    metrics = evaluate(FakeAnalyzer(), load_dataset())

    assert set(metrics.per_class["category"]) == {
        "bug",
        "feature",
        "documentation",
        "configuration",
        "performance",
    }
    assert set(metrics.confusion_matrix["priority"]) == {
        "low",
        "medium",
        "high",
        "urgent",
    }

    supports = sum(int(values["support"]) for values in metrics.per_class["category"].values())
    assert supports == metrics.valid_responses

    confusion_total = sum(
        sum(row.values()) for row in metrics.confusion_matrix["category"].values()
    )
    assert confusion_total == metrics.valid_responses


def test_confidence_calibration_covers_every_level() -> None:
    metrics = evaluate(FakeAnalyzer(), load_dataset())

    assert set(metrics.confidence_calibration) == {"low", "medium", "high"}
    assert (
        sum(int(values["cases"]) for values in metrics.confidence_calibration.values())
        == metrics.valid_responses
    )
    for values in metrics.confidence_calibration.values():
        assert int(values["fully_correct"]) <= int(values["cases"])
        assert 0 <= float(values["accuracy"]) <= 1


def test_errors_by_category_groups_failures_by_expected_category() -> None:
    class WrongCategoryAnalyzer:
        def analyze(self, incident: IncidentCreate) -> TriageResult:
            return TriageResult(
                category="feature",
                severity="low",
                priority="low",
                summary="Resultado fijo",
                affected_components=[],
                missing_information=[],
                justification="Resultado fijo para el test.",
                confidence="high",
            )

    cases = [
        EvaluationCase(
            id="bug-fails",
            input=IncidentCreate(title="Fallo", description="Descripción"),
            expected={
                "category": "bug",
                "severity": "medium",
                "priority": "medium",
                "missing_information": [],
                "confidence": "high",
            },
        ),
        EvaluationCase(
            id="feature-passes",
            input=IncidentCreate(title="Mejora", description="Descripción"),
            expected={
                "category": "feature",
                "severity": "low",
                "priority": "low",
                "missing_information": [],
                "confidence": "high",
            },
        ),
    ]

    metrics = evaluate(WrongCategoryAnalyzer(), cases)

    assert metrics.errors_by_category == {"bug": 1}


def test_missing_information_accuracy_ignores_expected_order() -> None:
    class TwoItemsAnalyzer:
        def analyze(self, incident: IncidentCreate) -> TriageResult:
            return TriageResult(
                category="bug",
                severity="medium",
                priority="medium",
                summary="Resultado fijo",
                affected_components=[],
                missing_information={"entorno", "logs"},
                justification="Resultado fijo para el test.",
                confidence="high",
            )

    expected = {
        "category": "bug",
        "severity": "medium",
        "priority": "medium",
        "missing_information": ["entorno", "logs"],
        "confidence": "high",
    }
    cases = [
        EvaluationCase(
            id="orden-directo",
            input=IncidentCreate(title="Fallo", description="Descripción"),
            expected=expected,
        ),
        EvaluationCase(
            id="orden-inverso",
            input=IncidentCreate(title="Fallo", description="Descripción"),
            expected={**expected, "missing_information": ["logs", "entorno"]},
        ),
    ]

    metrics = evaluate(TwoItemsAnalyzer(), cases)

    assert metrics.missing_information_accuracy == 1
    assert metrics.missing_information_precision == 1
    assert metrics.missing_information_recall == 1
    assert metrics.missing_information_f1 == 1


def test_evaluate_empty_dataset_returns_zero_metrics() -> None:
    metrics = evaluate(FakeAnalyzer(), [])

    assert metrics.total == 0
    assert metrics.valid_responses == 0
    assert metrics.errors == 0
    assert metrics.error_rate == 0
    assert metrics.latency_ms_total == 0
    assert metrics.latency_ms_average == 0
    assert metrics.latency_ms_p50 == 0
    assert metrics.latency_ms_p95 == 0
    assert metrics.category_macro_f1 == 0
    assert metrics.missing_information_f1 == 0
    assert metrics.errors_by_category == {}
    assert all(
        values["cases"] == 0 and values["accuracy"] == 0
        for values in metrics.confidence_calibration.values()
    )


def test_metrics_from_outcomes_matches_evaluate() -> None:
    cases = load_dataset()[:3]

    direct = evaluate(FakeAnalyzer(), cases)
    via_outcomes = metrics_from_outcomes(evaluate_cases(FakeAnalyzer(), cases))

    assert direct.category_accuracy == via_outcomes.category_accuracy
    assert direct.confusion_matrix == via_outcomes.confusion_matrix
