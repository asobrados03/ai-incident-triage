from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.analyzer import FakeAnalyzer, IncidentAnalyzer, OllamaAnalyzer
from app.schemas import IncidentCreate, TriageResult

DEFAULT_DATASET = (
    Path(__file__).resolve().parent.parent / "eval" / "data" / "incidents.json"
)


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    input: IncidentCreate
    expected: dict[str, Any]


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

    def as_dict(self) -> dict[str, int | float]:
        return asdict(self)


def load_dataset(path: Path = DEFAULT_DATASET) -> list[EvaluationCase]:
    with path.open(encoding="utf-8") as file:
        raw_cases = json.load(file)
    if not isinstance(raw_cases, list):
        raise ValueError("Evaluation dataset must contain a JSON array")
    return [EvaluationCase.model_validate(case) for case in raw_cases]


def evaluate(
    analyzer: IncidentAnalyzer,
    cases: list[EvaluationCase],
) -> EvaluationMetrics:
    total = len(cases)
    valid_responses = 0
    errors = 0
    latency_ms_total = 0.0
    category_hits = 0
    severity_hits = 0
    priority_hits = 0
    missing_hits = 0
    confidence_hits = 0

    for case in cases:
        started = time.perf_counter()
        try:
            result = analyzer.analyze(case.input)
            if not isinstance(result, TriageResult):
                raise TypeError("Analyzer result is not a TriageResult")
            valid_responses += 1
        except Exception:
            errors += 1
            latency_ms_total += (time.perf_counter() - started) * 1000
            continue
        latency_ms_total += (time.perf_counter() - started) * 1000

        expected = case.expected
        category_hits += result.category.value == expected["category"]
        severity_hits += result.severity.value == expected["severity"]
        priority_hits += result.priority.value == expected["priority"]
        missing_hits += result.missing_information == expected["missing_information"]
        confidence_hits += result.confidence.value == expected["confidence"]

    denominator = total or 1
    return EvaluationMetrics(
        total=total,
        valid_responses=valid_responses,
        category_accuracy=category_hits / denominator,
        severity_accuracy=severity_hits / denominator,
        priority_accuracy=priority_hits / denominator,
        missing_information_accuracy=missing_hits / denominator,
        confidence_accuracy=confidence_hits / denominator,
        errors=errors,
        error_rate=errors / denominator,
        latency_ms_total=latency_ms_total,
        latency_ms_average=latency_ms_total / denominator,
    )


def build_analyzer(backend: str) -> IncidentAnalyzer:
    if backend == "fake":
        return FakeAnalyzer()
    if backend == "ollama":
        return OllamaAnalyzer()
    raise ValueError(f"Unsupported evaluation backend: {backend}")


def main() -> None:
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
    args = parser.parse_args()

    metrics = evaluate(build_analyzer(args.backend), load_dataset(args.dataset))
    print(json.dumps(metrics.as_dict(), indent=2))


if __name__ == "__main__":
    main()
