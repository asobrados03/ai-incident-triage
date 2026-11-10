import os
import pytest
from backend.infrastructure.config import get_settings


@pytest.fixture(autouse=True)
def _isolate_test_settings(monkeypatch):
    monkeypatch.setenv("ANALYZER_BACKEND", "fake")
    monkeypatch.setenv("AUTH_USERS", "")
    monkeypatch.setenv("JWT_SECRET", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
