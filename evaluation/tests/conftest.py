"""Fixtures compartidas por los tests de evaluación."""

import pytest

from backend.api.schemas import IncidentCreate, TriageResult
from evaluation.runner import EvaluationCase, compare_outcomes, evaluate_cases


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


@pytest.fixture
def comparison_inputs():
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


@pytest.fixture
def comparison_result(comparison_inputs):
    cases, baseline, candidate = comparison_inputs
    return compare_outcomes(
        "baseline",
        evaluate_cases(baseline, cases),
        "candidate",
        evaluate_cases(candidate, cases),
    )
