import json

from app.evaluation import EvaluationCase, evaluate, load_dataset
from app.schemas import IncidentCreate, TriageResult
from app.analyzer import FakeAnalyzer


def test_load_reference_dataset_has_eight_cases() -> None:
    cases = load_dataset()

    assert len(cases) == 8
    assert all(case.input.title for case in cases)
    assert all("category" in case.expected for case in cases)


def test_fake_evaluation_is_reproducible() -> None:
    metrics = evaluate(FakeAnalyzer(), load_dataset())

    assert metrics.total == 8
    assert metrics.valid_responses == 8
    assert metrics.errors == 0
    assert metrics.error_rate == 0
    assert metrics.category_accuracy == 1
    assert metrics.severity_accuracy == 1
    assert metrics.priority_accuracy == 1
    assert metrics.missing_information_accuracy == 1
    assert metrics.confidence_accuracy == 1


def test_evaluate_empty_dataset_returns_zero_metrics() -> None:
    metrics = evaluate(FakeAnalyzer(), [])

    assert metrics.total == 0
    assert metrics.valid_responses == 0
    assert metrics.errors == 0
    assert metrics.error_rate == 0


def test_evaluate_counts_invalid_results_as_errors() -> None:
    class BrokenAnalyzer:
        def analyze(self, incident: IncidentCreate) -> TriageResult:
            raise RuntimeError("broken analyzer")

    case = EvaluationCase(
        id="broken",
        input=IncidentCreate(title="Fallo", description="Descripción"),
        expected={
            "category": "bug",
            "severity": "medium",
            "priority": "medium",
            "missing_information": [],
            "confidence": "high",
        },
    )

    metrics = evaluate(BrokenAnalyzer(), [case])

    assert metrics.total == 1
    assert metrics.valid_responses == 0
    assert metrics.errors == 1
    assert metrics.error_rate == 1


def test_evaluate_counts_non_triage_result_as_error() -> None:
    class InvalidAnalyzer:
        def analyze(self, incident: IncidentCreate):
            return {"category": "bug"}

    case = EvaluationCase(
        id="invalid",
        input=IncidentCreate(title="Fallo", description="Descripción"),
        expected={
            "category": "bug",
            "severity": "medium",
            "priority": "medium",
            "missing_information": [],
            "confidence": "high",
        },
    )

    metrics = evaluate(InvalidAnalyzer(), [case])

    assert metrics.valid_responses == 0
    assert metrics.errors == 1


def test_load_dataset_rejects_non_array(tmp_path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps({"id": "not-a-list"}), encoding="utf-8")

    try:
        load_dataset(path)
    except ValueError as error:
        assert "JSON array" in str(error)
    else:
        raise AssertionError("Expected ValueError")
