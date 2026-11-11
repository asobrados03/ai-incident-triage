from backend.analyzers.core import FakeAnalyzer
from backend.api.schemas import IncidentCreate, TriageResult
from evaluation.runner import (
    EvaluationCase,
    evaluate,
    evaluate_cases,
    load_dataset,
    print_comparison,
    print_outcomes,
    print_summary,
)


def test_print_summary_includes_calibration_and_error_analysis(capsys) -> None:
    print_summary(evaluate(FakeAnalyzer(), load_dataset()))

    captured = capsys.readouterr()
    assert "Resumen de evaluación" in captured.err
    assert "Calibración de confianza" in captured.err
    assert "Errores por categoría esperada" in captured.err


def test_print_comparison_reports_deltas_and_changed_cases(comparison_result, capsys) -> None:
    print_comparison(comparison_result)

    captured = capsys.readouterr()
    assert "Comparación baseline -> candidate" in captured.err
    assert "Mejoras: 1" in captured.err
    assert "Empeoramientos: 1" in captured.err
    assert "Mejoran: improves" in captured.err
    assert "Empeoran: worsens" in captured.err
    assert "category:" in captured.err
    assert "latency p50:" in captured.err


def test_print_outcomes_marks_failures(capsys) -> None:
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

    print_outcomes(evaluate_cases(BrokenAnalyzer(), [case]))

    captured = capsys.readouterr()
    assert "[FAIL] broken" in captured.err
    assert "broken analyzer" in captured.err
