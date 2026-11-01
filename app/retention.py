"""Backward-compatible CLI module for data retention."""

from app.services.retention import *  # noqa: F403


if __name__ == "__main__":
    from app.services.retention import main

    raise SystemExit(main())
