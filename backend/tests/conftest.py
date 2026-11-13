import pytest

from backend.api.dependencies import reset_login_throttle
from backend.infrastructure.config import get_settings


@pytest.fixture(autouse=True)
def _isolate_test_settings(monkeypatch):
    monkeypatch.setenv("ANALYZER_BACKEND", "fake")
    monkeypatch.setenv("AUTH_USERS", "")
    monkeypatch.setenv("JWT_SECRET", "")
    # La suite histórica usa acceso anónimo con BD vacía; el default de
    # producción es fail-closed y se cubre en test_security.py.
    monkeypatch.setenv("ALLOW_ANONYMOUS_BOOTSTRAP", "true")
    get_settings.cache_clear()
    reset_login_throttle()
    yield
    get_settings.cache_clear()
    reset_login_throttle()
