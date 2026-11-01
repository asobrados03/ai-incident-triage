"""Offline analyzer evaluation."""

from backend.evaluation import runner as _runner
from backend.evaluation.runner import *  # noqa: F403


def main() -> None:
    """Run the CLI while preserving the legacy module-level test hooks."""
    _runner.build_analyzer = build_analyzer
    _runner.load_dataset = load_dataset
    return _runner.main()
