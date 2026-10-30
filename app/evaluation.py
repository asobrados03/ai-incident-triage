from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import sys
import time
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.analyzer import FakeAnalyzer, IncidentAnalyzer, OllamaAnalyzer
from app.models import (
    AnalysisConfidence,
    IncidentCategory,
    IncidentPriority,
    IncidentSeverity,
)
from app.schemas import IncidentCreate, TriageResult

DEFAULT_DATASET = (
    Path(__file__).resolve().parent.parent / "eval" / "data" / "incidents.json"
)
DEFAULT_HOLDOUT_DATASET = (
    Path(__file__).resolve().parent.parent
    / "eval"
    / "data"
    / "incidents-holdout.json"
)
DEFAULT_HOLDOUT_V2_DATASET = (
    Path(__file__).resolve().parent.parent
    / "eval"
    / "data"
    / "incidents-holdout-v2.json"
)
DEFAULT_REGRESSION_DATASET = (
    Path(__file__).resolve().parent.parent
    / "eval"
    / "data"
    / "incidents-regression.json"
)

_ENUM_FIELDS: dict[str, tuple[str, ...]] = {
    "category": tuple(category.value for category in IncidentCategory),
    "severity": tuple(severity.value for severity in IncidentSeverity),
    "priority": tuple(priority.value for priority in IncidentPriority),
    "confidence": tuple(confidence.value for confidence in AnalysisConfidence),
}
_SCORED_FIELDS = (
    "category",
    "severity",
    "priority",
    "missing_information",
    "confidence",
)


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    input: IncidentCreate
    expected: dict[str, Any]


@dataclass(frozen=True)
class CaseOutcome:
    id: str
    valid: bool
    latency_ms: float
    expected: dict[str, Any]
    actual: dict[str, Any] | None = None
    mismatches: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class EvaluationMetrics:
    total: int
    valid_responses: int
    category_accuracy: float
    severity_accuracy: float
    priority_accuracy: float
    missing_information_accuracy: float
    confidence_accuracy: float
    errors: int
    error_rate: float
    latency_ms_total: float
    latency_ms_average: float
    latency_ms_p50: float
    latency_ms_p95: float
    category_macro_f1: float
    severity_macro_f1: float
    priority_macro_f1: float
    missing_information_precision: float
    missing_information_recall: float
    missing_information_f1: float
    per_class: dict[str, dict[str, dict[str, float | int]]]
    confusion_matrix: dict[str, dict[str, dict[str, int]]]
    confidence_calibration: dict[str, dict[str, float | int]]
    errors_by_category: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BackendComparison:
    baseline: str
    candidate: str
    baseline_metrics: EvaluationMetrics
    candidate_metrics: EvaluationMetrics
    improved: tuple[str, ...]
    worsened: tuple[str, ...]
    changed: tuple[str, ...]
    unchanged: tuple[str, ...]

    def deltas(self) -> dict[str, float]:
        fields = (
            "category_accuracy",
            "severity_accuracy",
            "priority_accuracy",
            "missing_information_accuracy",
            "confidence_accuracy",
            "category_macro_f1",
            "severity_macro_f1",
            "priority_macro_f1",
            "latency_ms_p50",
            "latency_ms_p95",
            "error_rate",
        )
        return {
            field: getattr(self.candidate_metrics, field)
            - getattr(self.baseline_metrics, field)
            for field in fields
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "baseline": {
                "backend": self.baseline,
                "metrics": self.baseline_metrics.as_dict(),
            },
            "candidate": {
                "backend": self.candidate,
                "metrics": self.candidate_metrics.as_dict(),
            },
            "deltas": self.deltas(),
            "cases": {
                "improved": list(self.improved),
                "worsened": list(self.worsened),
                "changed": list(self.changed),
                "unchanged": list(self.unchanged),
            },
        }


def load_dataset(path: Path = DEFAULT_DATASET) -> list[EvaluationCase]:
    with path.open(encoding="utf-8") as file:
        raw_cases = json.load(file)
    if not isinstance(raw_cases, list):
        raise ValueError("Evaluation dataset must contain a JSON array")
    return [EvaluationCase.model_validate(case) for case in raw_cases]


def evaluate_cases(
    analyzer: IncidentAnalyzer,
    cases: list[EvaluationCase],
) -> list[CaseOutcome]:
    outcomes: list[CaseOutcome] = []
    for case in cases:
        started = time.perf_counter()
        try:
            result = analyzer.analyze(case.input)
            if not isinstance(result, TriageResult):
                raise TypeError("Analyzer result is not a TriageResult")
        except Exception as error:  # noqa: BLE001 - metrics must count any failure
            outcomes.append(
                CaseOutcome(
                    id=case.id,
                    valid=False,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    expected=case.expected,
                    error=f"{type(error).__name__}: {error}",
                ),
            )
            continue

        actual = {
            "category": result.category.value,
            "severity": result.severity.value,
            "priority": result.priority.value,
            "missing_information": list(result.missing_information),
            "confidence": result.confidence.value,
        }
        mismatches = tuple(
            field
            for field in _SCORED_FIELDS
            if actual[field] != case.expected.get(field)
        )
        outcomes.append(
            CaseOutcome(
                id=case.id,
                valid=True,
                latency_ms=(time.perf_counter() - started) * 1000,
                expected=case.expected,
                actual=actual,
                mismatches=mismatches,
            ),
        )
    return outcomes


def evaluate(
    analyzer: IncidentAnalyzer,
    cases: list[EvaluationCase],
) -> EvaluationMetrics:
    return metrics_from_outcomes(evaluate_cases(analyzer, cases))


def metrics_from_outcomes(outcomes: list[CaseOutcome]) -> EvaluationMetrics:
    total = len(outcomes)
    valid_outcomes = [outcome for outcome in outcomes if outcome.valid]
    denominator = total or 1
    latencies = [outcome.latency_ms for outcome in outcomes]

    per_class: dict[str, dict[str, dict[str, float | int]]] = {}
    confusion_matrix: dict[str, dict[str, dict[str, int]]] = {}
    macro_f1: dict[str, float] = {}
    for field, labels in _ENUM_FIELDS.items():
        field_metrics, field_confusion = _class_metrics(
            valid_outcomes,
            field,
            labels,
        )
        per_class[field] = field_metrics
        confusion_matrix[field] = field_confusion
        macro_f1[field] = _macro_f1(field_metrics)

    missing_precision, missing_recall, missing_f1 = _missing_metrics(
        valid_outcomes,
    )

    return EvaluationMetrics(
        total=total,
        valid_responses=len(valid_outcomes),
        category_accuracy=_accuracy(valid_outcomes, "category", denominator),
        severity_accuracy=_accuracy(valid_outcomes, "severity", denominator),
        priority_accuracy=_accuracy(valid_outcomes, "priority", denominator),
        missing_information_accuracy=_accuracy(
            valid_outcomes,
            "missing_information",
            denominator,
        ),
        confidence_accuracy=_accuracy(valid_outcomes, "confidence", denominator),
        errors=total - len(valid_outcomes),
        error_rate=(total - len(valid_outcomes)) / denominator,
        latency_ms_total=sum(latencies),
        latency_ms_average=sum(latencies) / denominator,
        latency_ms_p50=_percentile(latencies, 0.50),
        latency_ms_p95=_percentile(latencies, 0.95),
        category_macro_f1=macro_f1["category"],
        severity_macro_f1=macro_f1["severity"],
        priority_macro_f1=macro_f1["priority"],
        missing_information_precision=missing_precision,
        missing_information_recall=missing_recall,
        missing_information_f1=missing_f1,
        per_class=per_class,
        confusion_matrix=confusion_matrix,
        confidence_calibration=_confidence_calibration(valid_outcomes),
        errors_by_category=_errors_by_category(outcomes),
    )


def compare_outcomes(
    baseline: str,
    baseline_outcomes: list[CaseOutcome],
    candidate: str,
    candidate_outcomes: list[CaseOutcome],
) -> BackendComparison:
    baseline_by_id = {outcome.id: outcome for outcome in baseline_outcomes}
    candidate_by_id = {outcome.id: outcome for outcome in candidate_outcomes}
    if set(baseline_by_id) != set(candidate_by_id):
        raise ValueError("Both backends must produce outcomes for the same case ids")

    improved: list[str] = []
    worsened: list[str] = []
    changed: list[str] = []
    unchanged: list[str] = []
    for case_id in baseline_by_id:
        baseline_outcome = baseline_by_id[case_id]
        candidate_outcome = candidate_by_id[case_id]
        baseline_correct = _is_fully_correct(baseline_outcome)
        candidate_correct = _is_fully_correct(candidate_outcome)
        if not baseline_correct and candidate_correct:
            improved.append(case_id)
        elif baseline_correct and not candidate_correct:
            worsened.append(case_id)
        elif (
            baseline_outcome.valid == candidate_outcome.valid
            and baseline_outcome.mismatches == candidate_outcome.mismatches
        ):
            unchanged.append(case_id)
        else:
            changed.append(case_id)

    return BackendComparison(
        baseline=baseline,
        candidate=candidate,
        baseline_metrics=metrics_from_outcomes(baseline_outcomes),
        candidate_metrics=metrics_from_outcomes(candidate_outcomes),
        improved=tuple(improved),
        worsened=tuple(worsened),
        changed=tuple(changed),
        unchanged=tuple(unchanged),
    )


def _is_fully_correct(outcome: CaseOutcome) -> bool:
    return outcome.valid and not outcome.mismatches


def _accuracy(
    outcomes: list[CaseOutcome],
    field: str,
    denominator: int,
) -> float:
    hits = sum(
        outcome.actual is not None
        and outcome.actual[field] == outcome.expected.get(field)
        for outcome in outcomes
    )
    return hits / denominator


def _class_metrics(
    outcomes: list[CaseOutcome],
    field: str,
    labels: tuple[str, ...],
) -> tuple[dict[str, dict[str, float | int]], dict[str, dict[str, int]]]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for outcome in outcomes:
        if outcome.actual is None:
            continue
        expected = outcome.expected.get(field)
        predicted = outcome.actual[field]
        if expected in labels and predicted in labels:
            counts[expected][predicted] += 1

    confusion = {
        expected: {predicted: counts[expected][predicted] for predicted in labels}
        for expected in labels
    }

    metrics: dict[str, dict[str, float | int]] = {}
    for label in labels:
        true_positive = counts[label][label]
        false_positive = sum(
            counts[expected][label]
            for expected in labels
            if expected != label
        )
        false_negative = sum(
            counts[label][predicted]
            for predicted in labels
            if predicted != label
        )
        precision = (
            true_positive / (true_positive + false_positive)
            if true_positive + false_positive
            else 0.0
        )
        recall = (
            true_positive / (true_positive + false_negative)
            if true_positive + false_negative
            else 0.0
        )
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
        metrics[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": sum(counts[label].values()),
        }
    return metrics, confusion


def _macro_f1(metrics: dict[str, dict[str, float | int]]) -> float:
    active = [
        float(values["f1"])
        for values in metrics.values()
        if values["support"] or values["f1"]
    ]
    return sum(active) / len(active) if active else 0.0


def _missing_metrics(
    outcomes: list[CaseOutcome],
) -> tuple[float, float, float]:
    if not outcomes:
        return 0.0, 0.0, 0.0

    true_positive = false_positive = false_negative = 0
    for outcome in outcomes:
        if outcome.actual is None:
            continue
        expected = set(outcome.expected.get("missing_information") or [])
        predicted = set(outcome.actual["missing_information"])
        true_positive += len(expected & predicted)
        false_positive += len(predicted - expected)
        false_negative += len(expected - predicted)

    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else 1.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else 1.0
    )
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return precision, recall, f1


def _confidence_calibration(
    outcomes: list[CaseOutcome],
) -> dict[str, dict[str, float | int]]:
    calibration: dict[str, dict[str, float | int]] = {}
    for level in AnalysisConfidence:
        level_outcomes = [
            outcome
            for outcome in outcomes
            if outcome.actual is not None
            and outcome.actual["confidence"] == level.value
        ]
        correct = sum(not outcome.mismatches for outcome in level_outcomes)
        calibration[level.value] = {
            "cases": len(level_outcomes),
            "fully_correct": correct,
            "accuracy": correct / len(level_outcomes) if level_outcomes else 0.0,
        }
    return calibration


def _errors_by_category(outcomes: list[CaseOutcome]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for outcome in outcomes:
        if outcome.valid and not outcome.mismatches:
            continue
        expected = outcome.expected.get("category")
        counts[expected if isinstance(expected, str) else "unknown"] += 1
    return dict(counts)


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * fraction
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def build_analyzer(backend: str) -> IncidentAnalyzer:
    if backend == "fake":
        return FakeAnalyzer()
    if backend == "ollama":
        return OllamaAnalyzer()
    raise ValueError(f"Unsupported evaluation backend: {backend}")


def print_outcomes(outcomes: list[CaseOutcome], file: Any = None) -> None:
    if file is None:
        file = sys.stderr
    for outcome in outcomes:
        status = "OK" if outcome.valid and not outcome.mismatches else "FAIL"
        print(
            f"[{status}] {outcome.id} ({outcome.latency_ms:.2f} ms)",
            file=file,
        )
        if not outcome.valid:
            print(f"  error: {outcome.error}", file=file)
            continue
        for field in outcome.mismatches:
            print(
                f"  {field}: expected={outcome.expected.get(field)!r} "
                f"actual={outcome.actual[field]!r}",  # type: ignore[index]
                file=file,
            )


def _top_confusions(
    confusion: dict[str, dict[str, int]],
    limit: int = 3,
) -> list[tuple[int, str, str]]:
    errors = [
        (count, expected, predicted)
        for expected, row in confusion.items()
        for predicted, count in row.items()
        if expected != predicted and count
    ]
    return sorted(errors, reverse=True)[:limit]


def print_summary(
    metrics: EvaluationMetrics,
    file: Any = None,
    label: str | None = None,
) -> None:
    if file is None:
        file = sys.stderr

    title = "Resumen de evaluación"
    if label:
        title = f"{title} ({label})"
    print(title, file=file)
    print(
        f"Casos: {metrics.total} | Válidos: {metrics.valid_responses} | "
        f"Errores: {metrics.errors}",
        file=file,
    )
    print(
        "Accuracy: "
        f"category={metrics.category_accuracy:.3f} "
        f"severity={metrics.severity_accuracy:.3f} "
        f"priority={metrics.priority_accuracy:.3f} "
        f"missing={metrics.missing_information_accuracy:.3f} "
        f"confidence={metrics.confidence_accuracy:.3f}",
        file=file,
    )
    print(
        "Macro-F1: "
        f"category={metrics.category_macro_f1:.3f} "
        f"severity={metrics.severity_macro_f1:.3f} "
        f"priority={metrics.priority_macro_f1:.3f}",
        file=file,
    )
    print("Calibración de confianza (nivel -> aciertos/casos):", file=file)
    for level, values in metrics.confidence_calibration.items():
        print(
            f"  {level}: {values['fully_correct']}/{values['cases']} "
            f"({values['accuracy']:.3f})",
            file=file,
        )

    if metrics.errors_by_category:
        errors = ", ".join(
            f"{category}={count}"
            for category, count in sorted(metrics.errors_by_category.items())
        )
        print(f"Errores por categoría esperada: {errors}", file=file)
    else:
        print("Errores por categoría esperada: ninguno", file=file)

    for field in ("category", "severity", "priority"):
        confusions = _top_confusions(metrics.confusion_matrix[field])
        if confusions:
            formatted = ", ".join(
                f"{expected}->{predicted}={count}"
                for count, expected, predicted in confusions
            )
            print(f"Confusiones {field}: {formatted}", file=file)


def print_comparison(comparison: BackendComparison, file: Any = None) -> None:
    if file is None:
        file = sys.stderr

    baseline = comparison.baseline_metrics
    candidate = comparison.candidate_metrics
    total = baseline.total
    print(
        f"Comparación {comparison.baseline} -> {comparison.candidate}",
        file=file,
    )
    print(
        f"Casos: {total} | Mejoras: {len(comparison.improved)} | "
        f"Empeoramientos: {len(comparison.worsened)} | "
        f"Cambios: {len(comparison.changed)} | "
        f"Sin cambios: {len(comparison.unchanged)}",
        file=file,
    )
    print("Métricas (baseline -> candidato, delta):", file=file)
    fields = (
        ("category", "category_accuracy"),
        ("severity", "severity_accuracy"),
        ("priority", "priority_accuracy"),
        ("missing", "missing_information_accuracy"),
        ("confidence", "confidence_accuracy"),
    )
    for label, field in fields:
        before = getattr(baseline, field)
        after = getattr(candidate, field)
        print(
            f"  {label}: {before:.3f} -> {after:.3f} ({after - before:+.3f})",
            file=file,
        )
    for label, field in (
        ("macro-F1 category", "category_macro_f1"),
        ("macro-F1 severity", "severity_macro_f1"),
        ("macro-F1 priority", "priority_macro_f1"),
    ):
        before = getattr(baseline, field)
        after = getattr(candidate, field)
        print(
            f"  {label}: {before:.3f} -> {after:.3f} ({after - before:+.3f})",
            file=file,
        )
    print(
        f"  latency p50: {baseline.latency_ms_p50:.2f} -> "
        f"{candidate.latency_ms_p50:.2f} ms "
        f"({candidate.latency_ms_p50 - baseline.latency_ms_p50:+.2f})",
        file=file,
    )
    print(
        f"  latency p95: {baseline.latency_ms_p95:.2f} -> "
        f"{candidate.latency_ms_p95:.2f} ms "
        f"({candidate.latency_ms_p95 - baseline.latency_ms_p95:+.2f})",
        file=file,
    )
    print(
        f"  errors: {baseline.errors} -> {candidate.errors} "
        f"({candidate.errors - baseline.errors:+d})",
        file=file,
    )

    for title, case_ids in (
        ("Mejoran", comparison.improved),
        ("Empeoran", comparison.worsened),
        ("Cambian sin pasar a correcto", comparison.changed),
    ):
        if case_ids:
            print(f"{title}: {', '.join(case_ids)}", file=file)


def _configure_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass


def main() -> None:
    _configure_output_encoding()
    parser = argparse.ArgumentParser(description="Evaluate an incident analyzer")
    parser.add_argument(
        "--backend",
        choices=("fake", "ollama"),
        default="fake",
        help="Analyzer backend; fake is the offline default",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help="Path to a JSON evaluation dataset",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-case expected/actual mismatches to stderr",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print aggregate metrics and confidence calibration to stderr",
    )
    parser.add_argument(
        "--compare-with",
        choices=("fake", "ollama"),
        help=(
            "Run a second backend on the same dataset and report metric deltas; "
            "must differ from --backend"
        ),
    )
    args = parser.parse_args()

    cases = load_dataset(args.dataset)
    if args.compare_with is not None:
        if args.compare_with == args.backend:
            parser.error("--compare-with must be different from --backend")
        baseline_outcomes = evaluate_cases(build_analyzer(args.backend), cases)
        candidate_outcomes = evaluate_cases(
            build_analyzer(args.compare_with),
            cases,
        )
        comparison = compare_outcomes(
            args.backend,
            baseline_outcomes,
            args.compare_with,
            candidate_outcomes,
        )
        if args.verbose:
            print(f"Resultados {args.backend}", file=sys.stderr)
            print_outcomes(baseline_outcomes)
            print(f"Resultados {args.compare_with}", file=sys.stderr)
            print_outcomes(candidate_outcomes)
        if args.summary:
            print_summary(comparison.baseline_metrics, label=args.backend)
            print_summary(comparison.candidate_metrics, label=args.compare_with)
        print_comparison(comparison)
        print(json.dumps(comparison.as_dict(), indent=2))
        return

    outcomes = evaluate_cases(build_analyzer(args.backend), cases)
    metrics = metrics_from_outcomes(outcomes)
    if args.verbose:
        print_outcomes(outcomes)
    if args.summary:
        print_summary(metrics)
    print(json.dumps(metrics.as_dict(), indent=2))


if __name__ == "__main__":
    main()
