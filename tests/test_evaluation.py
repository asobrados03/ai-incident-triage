import json
from pathlib import Path
import sys

from backend import evaluation as evaluation_module
from backend.analyzers.core import FakeAnalyzer
from backend.evaluation import (
    DEFAULT_HOLDOUT_DATASET,
    DEFAULT_HOLDOUT_V2_DATASET,
    DEFAULT_REGRESSION_DATASET,
    EvaluationCase,
    compare_outcomes,
    evaluate,
    evaluate_cases,
    load_dataset,
    metrics_from_outcomes,
    print_comparison,
    print_outcomes,
    print_summary,
)
from backend.schemas import IncidentCreate, TriageResult


def _triage(
    category: str,
    severity: str,
    priority: str,
    confidence: str = "high",
) -> TriageResult:
    return TriageResult(
        category=category,
        severity=severity,
        priority=priority,
        summary="Resultado fijo",
        affected_components=[],
        missing_information=[],
        justification="Resultado fijo para el test.",
        confidence=confidence,
    )


def _comparison_inputs():
    expected = {
        "improves": {
            "category": "bug",
            "severity": "medium",
            "priority": "medium",
            "missing_information": [],
            "confidence": "high",
        },
        "worsens": {
            "category": "feature",
            "severity": "low",
            "priority": "low",
            "missing_information": [],
            "confidence": "high",
        },
        "both-correct": {
            "category": "feature",
            "severity": "low",
            "priority": "low",
            "missing_information": [],
            "confidence": "high",
        },
        "same-failure": {
            "category": "documentation",
            "severity": "low",
            "priority": "medium",
            "missing_information": [],
            "confidence": "high",
        },
        "changed": {
            "category": "configuration",
            "severity": "medium",
            "priority": "high",
            "missing_information": [],
            "confidence": "high",
        },
    }
    cases = [
        EvaluationCase(
            id=case_id,
            input=IncidentCreate(title=case_id, description="Descripción"),
            expected=case_expected,
        )
        for case_id, case_expected in expected.items()
    ]

    class MappingAnalyzer:
        def __init__(self, results: dict[str, TriageResult]) -> None:
            self.results = results

        def analyze(self, incident: IncidentCreate) -> TriageResult:
            return self.results[incident.title]

    bug = _triage("bug", "medium", "medium")
    feature = _triage("feature", "low", "low")
    baseline = MappingAnalyzer(
        {
            "improves": feature,
            "worsens": feature,
            "both-correct": feature,
            "same-failure": bug,
            "changed": bug,
        },
    )
    candidate = MappingAnalyzer(
        {
            "improves": bug,
            "worsens": bug,
            "both-correct": feature,
            "same-failure": bug,
            "changed": _triage("bug", "high", "high"),
        },
    )
    return cases, baseline, candidate


def _comparison_fixture():
    cases, baseline, candidate = _comparison_inputs()
    return compare_outcomes(
        "baseline",
        evaluate_cases(baseline, cases),
        "candidate",
        evaluate_cases(candidate, cases),
    )


def test_load_reference_dataset_has_balanced_cases() -> None:
    cases = load_dataset()

    assert len(cases) == 28
    assert len({case.id for case in cases}) == len(cases)
    assert all(case.input.title for case in cases)
    assert all(
        {
            "category",
            "severity",
            "priority",
            "missing_information",
            "confidence",
        }
        <= case.expected.keys()
        for case in cases
    )
    assert {case.expected["category"] for case in cases} == {
        "bug",
        "feature",
        "documentation",
        "configuration",
        "performance",
    }
    assert {case.expected["severity"] for case in cases} == {
        "low",
        "medium",
        "high",
        "critical",
    }

    latency_case = next(
        case for case in cases if case.id == "occasional-incident-creation-latency"
    )
    assert latency_case.expected["missing_information"] == [
        "latencia observada",
        "porcentaje de peticiones afectadas",
        "momento en que ocurre",
        "identificador de correlación",
        "logs o métricas disponibles",
    ]


def test_holdout_dataset_is_separate_from_the_development_set() -> None:
    development = load_dataset()
    holdout = load_dataset(DEFAULT_HOLDOUT_DATASET)

    assert len(holdout) == 12
    assert not {case.id for case in development} & {case.id for case in holdout}


def test_all_holdouts_and_regression_sets_have_disjoint_ids() -> None:
    datasets = [
        load_dataset(path)
        for path in (
            DEFAULT_HOLDOUT_DATASET,
            DEFAULT_HOLDOUT_V2_DATASET,
            DEFAULT_REGRESSION_DATASET,
        )
    ]
    ids = [{case.id for case in cases} for cases in datasets]

    for index, current in enumerate(ids):
        assert len(current) == 12
        for other in ids[index + 1 :]:
            assert not current & other
        assert not current & {case.id for case in load_dataset()}


def test_blind_holdout_covers_every_category_and_severity() -> None:
    cases = load_dataset(DEFAULT_HOLDOUT_V2_DATASET)

    assert {case.expected["category"] for case in cases} == {
        "bug",
        "feature",
        "documentation",
        "configuration",
        "performance",
    }
    assert {case.expected["severity"] for case in cases} == {
        "low",
        "medium",
        "high",
        "critical",
    }


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

    supports = sum(
        int(values["support"]) for values in metrics.per_class["category"].values()
    )
    assert supports == metrics.valid_responses

    confusion_total = sum(
        sum(row.values())
        for row in metrics.confusion_matrix["category"].values()
    )
    assert confusion_total == metrics.valid_responses


def test_confidence_calibration_covers_every_level() -> None:
    metrics = evaluate(FakeAnalyzer(), load_dataset())

    assert set(metrics.confidence_calibration) == {"low", "medium", "high"}
    assert (
        sum(
            int(values["cases"])
            for values in metrics.confidence_calibration.values()
        )
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


def test_print_summary_includes_calibration_and_error_analysis(capsys) -> None:
    print_summary(evaluate(FakeAnalyzer(), load_dataset()))

    captured = capsys.readouterr()
    assert "Resumen de evaluación" in captured.err
    assert "Calibración de confianza" in captured.err
    assert "Errores por categoría esperada" in captured.err


def test_compare_outcomes_classifies_improvements_and_worsenings() -> None:
    comparison = _comparison_fixture()

    assert comparison.improved == ("improves",)
    assert comparison.worsened == ("worsens",)
    assert set(comparison.unchanged) == {"both-correct", "same-failure"}
    assert comparison.changed == ("changed",)
    assert comparison.baseline_metrics.total == 5
    assert comparison.candidate_metrics.total == 5
    assert "category_accuracy" in comparison.deltas()


def test_compare_outcomes_serializes_metrics_and_case_groups() -> None:
    payload = _comparison_fixture().as_dict()

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


def test_print_comparison_reports_deltas_and_changed_cases(capsys) -> None:
    print_comparison(_comparison_fixture())

    captured = capsys.readouterr()
    assert "Comparación baseline -> candidate" in captured.err
    assert "Mejoras: 1" in captured.err
    assert "Empeoramientos: 1" in captured.err
    assert "Mejoran: improves" in captured.err
    assert "Empeoran: worsens" in captured.err
    assert "category:" in captured.err
    assert "latency p50:" in captured.err


def test_main_compare_mode_uses_two_backends(monkeypatch, capsys) -> None:
    cases, baseline, candidate = _comparison_inputs()
    analyzers = {"fake": baseline, "ollama": candidate}
    monkeypatch.setattr(
        evaluation_module,
        "build_analyzer",
        lambda backend: analyzers[backend],
    )
    monkeypatch.setattr(evaluation_module, "load_dataset", lambda path: cases)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluation",
            "--backend",
            "fake",
            "--compare-with",
            "ollama",
            "--summary",
        ],
    )

    evaluation_module.main()

    captured = capsys.readouterr()
    assert "Comparación fake -> ollama" in captured.err
    assert "Resumen de evaluación (fake)" in captured.err
    assert "Resumen de evaluación (ollama)" in captured.err
    payload = json.loads(captured.out)
    assert payload["baseline"]["backend"] == "fake"
    assert payload["candidate"]["backend"] == "ollama"
    assert payload["cases"]["improved"] == ["improves"]


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


def test_metrics_from_outcomes_matches_evaluate() -> None:
    cases = load_dataset()[:3]

    direct = evaluate(FakeAnalyzer(), cases)
    via_outcomes = metrics_from_outcomes(evaluate_cases(FakeAnalyzer(), cases))

    assert direct.category_accuracy == via_outcomes.category_accuracy
    assert direct.confusion_matrix == via_outcomes.confusion_matrix


def test_load_dataset_rejects_non_array(tmp_path: Path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps({"id": "not-a-list"}), encoding="utf-8")

    try:
        load_dataset(path)
    except ValueError as error:
        assert "JSON array" in str(error)
    else:
        raise AssertionError("Expected ValueError")
