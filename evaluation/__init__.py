"""Offline analyzer evaluation."""

from evaluation import runner as _runner
from evaluation.runner import build_analyzer, load_dataset


def main() -> None:
    """Run the CLI while preserving the legacy module-level test hooks."""
    _runner.build_analyzer = build_analyzer
    _runner.load_dataset = load_dataset
    return _runner.main()
