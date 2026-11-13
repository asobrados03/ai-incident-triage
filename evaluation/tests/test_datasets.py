import json
from pathlib import Path

import pytest

from evaluation.runner import (
    DEFAULT_HOLDOUT_DATASET,
    DEFAULT_HOLDOUT_V2_DATASET,
    DEFAULT_REGRESSION_DATASET,
    load_dataset,
)


def valid_case(case_id: str = "case-1") -> dict:
    return {
        "id": case_id,
        "input": {"title": "Fallo", "description": "No funciona."},
        "expected": {
            "category": "bug",
            "severity": "medium",
            "priority": "medium",
            "missing_information": ["logs"],
            "confidence": "high",
        },
    }


def write_dataset(tmp_path: Path, raw: object) -> Path:
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


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
    path = write_dataset(tmp_path, {"id": "not-a-list"})

    try:
        load_dataset(path)
    except ValueError as error:
        assert "JSON array" in str(error)
    else:
        raise AssertionError("Expected ValueError")


def test_load_dataset_rejects_empty_dataset(tmp_path: Path) -> None:
    path = write_dataset(tmp_path, [])

    with pytest.raises(ValueError, match="at least one case"):
        load_dataset(path)


def test_load_dataset_rejects_duplicate_ids(tmp_path: Path) -> None:
    path = write_dataset(tmp_path, [valid_case("repetido"), valid_case("repetido")])

    with pytest.raises(ValueError, match="duplicate ids"):
        load_dataset(path)


def test_load_dataset_rejects_unknown_expected_keys(tmp_path: Path) -> None:
    case = valid_case()
    case["expected"]["impact"] = "high"
    path = write_dataset(tmp_path, [case])

    with pytest.raises(ValueError, match="expected must contain exactly"):
        load_dataset(path)


def test_load_dataset_rejects_missing_expected_keys(tmp_path: Path) -> None:
    case = valid_case()
    del case["expected"]["confidence"]
    path = write_dataset(tmp_path, [case])

    with pytest.raises(ValueError, match="expected must contain exactly"):
        load_dataset(path)


@pytest.mark.parametrize("field", ["category", "severity", "priority", "confidence"])
def test_load_dataset_rejects_invalid_enums(tmp_path: Path, field: str) -> None:
    case = valid_case()
    case["expected"][field] = "not-a-valid-value"
    path = write_dataset(tmp_path, [case])

    with pytest.raises(ValueError, match=f"expected.{field} must be one of"):
        load_dataset(path)


def test_load_dataset_rejects_non_list_missing_information(tmp_path: Path) -> None:
    case = valid_case()
    case["expected"]["missing_information"] = "logs"
    path = write_dataset(tmp_path, [case])

    with pytest.raises(ValueError, match="list of non-empty strings"):
        load_dataset(path)


def test_load_dataset_rejects_empty_missing_information_items(tmp_path: Path) -> None:
    case = valid_case()
    case["expected"]["missing_information"] = ["logs", ""]
    path = write_dataset(tmp_path, [case])

    with pytest.raises(ValueError, match="list of non-empty strings"):
        load_dataset(path)


def test_load_dataset_rejects_duplicate_missing_information(tmp_path: Path) -> None:
    case = valid_case()
    case["expected"]["missing_information"] = ["logs", "logs"]
    path = write_dataset(tmp_path, [case])

    with pytest.raises(ValueError, match="must not contain duplicates"):
        load_dataset(path)
