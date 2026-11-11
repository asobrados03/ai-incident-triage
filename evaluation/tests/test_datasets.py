import json
from pathlib import Path

from evaluation.runner import (
    DEFAULT_HOLDOUT_DATASET,
    DEFAULT_HOLDOUT_V2_DATASET,
    DEFAULT_REGRESSION_DATASET,
    load_dataset,
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

    latency_case = next(case for case in cases if case.id == "occasional-incident-creation-latency")
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


def test_load_dataset_rejects_non_array(tmp_path: Path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps({"id": "not-a-list"}), encoding="utf-8")

    try:
        load_dataset(path)
    except ValueError as error:
        assert "JSON array" in str(error)
    else:
        raise AssertionError("Expected ValueError")
