import pytest

from backend.infrastructure.config import Settings, validate_runtime_settings
from backend.security.login_throttle import LoginThrottle


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_blocks_after_max_attempts_and_reports_retry_after() -> None:
    clock = FakeClock()
    throttle = LoginThrottle(max_attempts=3, window_seconds=60, clock=clock)

    for _ in range(3):
        assert throttle.retry_after("writer", "127.0.0.1") is None
        throttle.record_failure("writer", "127.0.0.1")

    assert throttle.retry_after("writer", "127.0.0.1") == 60
    clock.advance(15)
    assert throttle.retry_after("writer", "127.0.0.1") == 45


def test_retry_after_is_never_below_one_second() -> None:
    clock = FakeClock()
    throttle = LoginThrottle(max_attempts=1, window_seconds=10, clock=clock)
    throttle.record_failure("writer", "127.0.0.1")

    clock.advance(9.9)

    assert throttle.retry_after("writer", "127.0.0.1") == 1


def test_window_expiry_allows_a_new_attempt() -> None:
    clock = FakeClock()
    throttle = LoginThrottle(max_attempts=1, window_seconds=60, clock=clock)
    throttle.record_failure("writer", "127.0.0.1")
    assert throttle.retry_after("writer", "127.0.0.1") == 60

    clock.advance(60)

    assert throttle.retry_after("writer", "127.0.0.1") is None
    throttle.record_failure("writer", "127.0.0.1")
    assert throttle.retry_after("writer", "127.0.0.1") == 60


def test_success_resets_the_counter() -> None:
    throttle = LoginThrottle(max_attempts=2, window_seconds=60)
    throttle.record_failure("writer", "127.0.0.1")
    throttle.record_failure("writer", "127.0.0.1")
    assert throttle.retry_after("writer", "127.0.0.1") is not None

    throttle.reset("writer", "127.0.0.1")

    assert throttle.retry_after("writer", "127.0.0.1") is None


def test_counters_are_isolated_by_username_and_client() -> None:
    clock = FakeClock()
    throttle = LoginThrottle(max_attempts=1, window_seconds=60, clock=clock)
    throttle.record_failure("writer", "127.0.0.1")

    assert throttle.retry_after("writer", "127.0.0.1") is not None
    assert throttle.retry_after("reader", "127.0.0.1") is None
    assert throttle.retry_after("writer", "10.0.0.2") is None


def test_username_matching_ignores_case_and_surrounding_spaces() -> None:
    throttle = LoginThrottle(max_attempts=1, window_seconds=60)
    throttle.record_failure("  Writer ", "127.0.0.1")

    assert throttle.retry_after("writer", "127.0.0.1") is not None


def test_expired_windows_are_pruned_when_the_table_grows() -> None:
    clock = FakeClock()
    throttle = LoginThrottle(max_attempts=1, window_seconds=60, clock=clock)

    for index in range(2050):
        throttle.record_failure(f"user-{index}", "127.0.0.1")
    assert throttle.tracked_windows == 2050

    clock.advance(60)
    throttle.record_failure("nuevo", "127.0.0.1")

    assert throttle.tracked_windows == 1


def test_invalid_configuration_is_rejected() -> None:
    with pytest.raises(ValueError):
        LoginThrottle(max_attempts=0)
    with pytest.raises(ValueError):
        LoginThrottle(window_seconds=0)


def test_settings_reject_invalid_throttle_limits() -> None:
    with pytest.raises(ValueError):
        validate_runtime_settings(Settings(login_max_attempts=0))
    with pytest.raises(ValueError):
        validate_runtime_settings(Settings(login_window_seconds=0))
