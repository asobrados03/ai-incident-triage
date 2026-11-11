import json
import sys

import evaluation as evaluation_module


def test_main_compare_mode_uses_two_backends(comparison_inputs, monkeypatch, capsys) -> None:
    cases, baseline, candidate = comparison_inputs
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
