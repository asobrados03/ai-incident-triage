"""Offline analyzer evaluation."""

from app.evaluation import runner as _runner
from app.evaluation.runner import *  # noqa: F403


def main() -> None:
    """Run the CLI while preserving the legacy module-level test hooks."""
    _runner.build_analyzer = build_analyzer
    _runner.load_dataset = load_dataset
    return _runner.main()
