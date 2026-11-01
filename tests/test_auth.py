import pytest

from backend.auth import (
    Principal,
    Role,
    create_access_token,
    get_auth_user_store,
    parse_auth_users,
)
from backend.infrastructure.config import Settings, get_cors_origins, validate_runtime_settings


VALID_READER_PASSWORD = "reader-password-0123456789"
VALID_ADMIN_PASSWORD = "admin-password-0123456789"
AUTH_USERS = (
    f"reader:reader:{VALID_READER_PASSWORD},"
    f"admin:admin:{VALID_ADMIN_PASSWORD}"
)
JWT_SECRET = "test-jwt-secret-that-is-long-enough-123456"


def test_empty_auth_users_disable_authentication() -> None:
    store = parse_auth_users("")

    assert not store.enabled


def test_parse_auth_users_authenticates_each_role() -> None:
    store = parse_auth_users(AUTH_USERS)

    assert store.enabled
    assert store.authenticate("reader", VALID_READER_PASSWORD) == Principal(
        name="reader",
        role=Role.READER,
    )
    assert store.authenticate("admin", VALID_ADMIN_PASSWORD) == Principal(
        name="admin",
        role=Role.ADMIN,
    )
    assert store.authenticate("reader", "wrong-password") is None


def test_settings_repr_does_not_expose_auth_secrets() -> None:
    settings = Settings(
        auth_users=AUTH_USERS,
        jwt_secret=JWT_SECRET,
    )

    assert VALID_READER_PASSWORD not in repr(settings)
    assert JWT_SECRET not in repr(settings)
    assert VALID_ADMIN_PASSWORD not in str(settings)


def test_jwt_token_contains_authenticated_principal() -> None:
    settings = Settings(
        auth_users=AUTH_USERS,
        jwt_secret=JWT_SECRET,
        jwt_expiration_minutes=15,
    )
    token = create_access_token(
        Principal(name="reader", role=Role.READER),
        settings,
    )
    assert isinstance(token, str)
    assert len(token.split(".")) == 3


def test_roles_are_hierarchical() -> None:
    reader = Principal(name="reader", role=Role.READER)
    writer = Principal(name="writer", role=Role.WRITER)
    admin = Principal(name="admin", role=Role.ADMIN)

    assert reader.has_at_least(Role.READER)
    assert not reader.has_at_least(Role.WRITER)
    assert writer.has_at_least(Role.READER)
    assert writer.has_at_least(Role.WRITER)
    assert not writer.has_at_least(Role.ADMIN)
    assert admin.has_at_least(Role.ADMIN)


@pytest.mark.parametrize(
    "raw",
    [
        "missing-fields:reader",
        "unsupported:owner:0123456789abcdef",
        ":reader:0123456789abcdef",
        "reader:reader:",
        "duplicate:reader:one,duplicate:admin:two",
    ],
)
def test_invalid_auth_users_configuration_is_rejected(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_auth_users(raw)


def test_jwt_configuration_requires_a_long_secret() -> None:
    with pytest.raises(ValueError):
        validate_runtime_settings(
            Settings(auth_users="reader:reader:password", jwt_secret="too-short"),
        )


def test_cors_rejects_wildcard() -> None:
    with pytest.raises(ValueError):
        get_cors_origins("*")


def test_cors_defaults_to_local_frontend() -> None:
    assert get_cors_origins("http://localhost:5173") == ["http://localhost:5173"]
