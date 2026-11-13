from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

_PRUNE_THRESHOLD = 2048


@dataclass
class _Window:
    attempts: int
    started_at: float


class LoginThrottle:
    """Ventana fija de intentos fallidos por usuario y cliente.

    El estado vive en memoria del proceso: protege un único worker. Con varios
    workers o instancias cada uno mantiene su propio contador, así que un
    despliegue real necesita un limitador compartido (Redis u otro) o dejarlo
    en el proxy. No sustituye a Argon2id ni a la revocación de tokens.
    """

    def __init__(
        self,
        *,
        max_attempts: int = 5,
        window_seconds: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_attempts <= 0:
            raise ValueError("max_attempts must be greater than zero")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be greater than zero")
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._clock = clock
        self._windows: dict[tuple[str, str], _Window] = {}
        self._lock = threading.Lock()

    def retry_after(self, username: str, client: str) -> int | None:
        """Segundos que faltan para poder reintentar, o `None` si no está bloqueado."""
        key = self._key(username, client)
        with self._lock:
            window = self._windows.get(key)
            if window is None:
                return None
            elapsed = self._clock() - window.started_at
            if elapsed >= self._window_seconds:
                del self._windows[key]
                return None
            if window.attempts < self._max_attempts:
                return None
            return max(1, math.ceil(self._window_seconds - elapsed))

    def record_failure(self, username: str, client: str) -> None:
        key = self._key(username, client)
        now = self._clock()
        with self._lock:
            self._prune_expired(now)
            window = self._windows.get(key)
            if window is None or now - window.started_at >= self._window_seconds:
                self._windows[key] = _Window(attempts=1, started_at=now)
                return
            window.attempts += 1

    def reset(self, username: str, client: str) -> None:
        with self._lock:
            self._windows.pop(self._key(username, client), None)

    def clear(self) -> None:
        with self._lock:
            self._windows.clear()

    @property
    def tracked_windows(self) -> int:
        with self._lock:
            return len(self._windows)

    def _prune_expired(self, now: float) -> None:
        if len(self._windows) < _PRUNE_THRESHOLD:
            return
        expired = [
            key
            for key, window in self._windows.items()
            if now - window.started_at >= self._window_seconds
        ]
        for key in expired:
            del self._windows[key]

    @staticmethod
    def _key(username: str, client: str) -> tuple[str, str]:
        return (username.strip().lower(), client)
