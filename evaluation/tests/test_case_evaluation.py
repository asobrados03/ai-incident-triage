from backend.api.schemas import IncidentCreate, TriageResult
from evaluation.runner import EvaluationCase, evaluate, evaluate_cases


def test_evaluate_cases_reports_mismatches_per_case() -> None:
    class FixedAnalyzer:
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

    case = EvaluationCase(
        id="fixed",
        input=IncidentCreate(title="Fallo", description="Descripción"),
        expected={
            "category": "bug",
            "severity": "medium",
            "priority": "medium",
            "missing_information": [],
            "confidence": "high",
        },
    )

    outcome = evaluate_cases(FixedAnalyzer(), [case])[0]

    assert outcome.valid is True
    assert outcome.mismatches == ("category", "severity", "priority")
    assert outcome.actual is not None
    assert outcome.actual["category"] == "feature"


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
