import jwt
import pytest

from backend.auth import (
    BootstrapUser,
    Principal,
    Role,
    create_access_token,
    create_refresh_token,
    hash_password,
    parse_auth_users,
    verify_password,
    verify_refresh_token,
)
from backend.infrastructure.config import (
    Settings,
    get_cors_origins,
    validate_runtime_settings,
)


VALID_READER_PASSWORD = "reader-password-0123456789"
VALID_ADMIN_PASSWORD = "admin-password-0123456789"
AUTH_USERS = (
    f"reader:reader:{VALID_READER_PASSWORD},"
    f"admin:admin:{VALID_ADMIN_PASSWORD}"
)
JWT_SECRET = "test-jwt-secret-that-is-long-enough-123456"


def test_empty_auth_users_produce_no_bootstrap_users() -> None:
    assert parse_auth_users("") == ()


def test_parse_auth_users_returns_bootstrap_entries() -> None:
    users = parse_auth_users(AUTH_USERS)

    assert users == (
        BootstrapUser(
            username="reader",
            role=Role.READER,
            password=VALID_READER_PASSWORD,
        ),
        BootstrapUser(
            username="admin",
            role=Role.ADMIN,
            password=VALID_ADMIN_PASSWORD,
        ),
    )


def test_passwords_are_hashed_with_argon2_and_unique_salts() -> None:
    first = hash_password(VALID_READER_PASSWORD)
    second = hash_password(VALID_READER_PASSWORD)

    assert first.startswith("$argon2")
    assert first != second
    assert VALID_READER_PASSWORD not in first
    assert verify_password(VALID_READER_PASSWORD, first)
    assert verify_password(VALID_READER_PASSWORD, second)
    assert not verify_password("wrong-password", first)


def test_verify_password_rejects_invalid_hashes() -> None:
    assert not verify_password(VALID_READER_PASSWORD, None)
    assert not verify_password(VALID_READER_PASSWORD, "not-a-valid-hash")


def test_short_passwords_are_rejected() -> None:
    with pytest.raises(ValueError):
        hash_password("short")


def test_settings_repr_does_not_expose_auth_secrets() -> None:
    settings = Settings(
        auth_users=AUTH_USERS,
        jwt_secret=JWT_SECRET,
    )

    assert VALID_READER_PASSWORD not in repr(settings)
    assert JWT_SECRET not in repr(settings)
    assert VALID_ADMIN_PASSWORD not in str(settings)


def test_jwt_token_contains_versioned_principal() -> None:
    settings = Settings(
        auth_users=AUTH_USERS,
        jwt_secret=JWT_SECRET,
        jwt_expiration_minutes=15,
        refresh_token_expiration_days=7,
    )
    token = create_access_token(
        Principal(name="reader", role=Role.READER),
        settings,
        token_version=3,
    )
    payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])

    assert payload["sub"] == "reader"
    assert payload["role"] == "reader"
    assert payload["ver"] == 3
    assert payload["typ"] == "access"
    assert "iat" in payload
    assert payload["exp"] > payload["iat"]

    refresh_token = create_refresh_token(
        Principal(name="reader", role=Role.READER),
        settings,
        token_version=3,
    )
    refresh_payload = jwt.decode(refresh_token, JWT_SECRET, algorithms=["HS256"])
    assert refresh_payload["sub"] == "reader"
    assert refresh_payload["ver"] == 3
    assert refresh_payload["typ"] == "refresh"
    assert "iat" in refresh_payload
    assert refresh_payload["exp"] > payload["exp"]


def test_token_creation_requires_a_long_secret() -> None:
    with pytest.raises(ValueError):
        create_access_token(
            Principal(name="reader", role=Role.READER),
            Settings(jwt_secret="too-short"),
        )
    with pytest.raises(ValueError):
        create_refresh_token(
            Principal(name="reader", role=Role.READER),
            Settings(jwt_secret="too-short"),
        )


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
        "duplicate:reader:0123456789abcdef,duplicate:admin:0123456789abcdef",
        "ab:reader:0123456789abcdef",
        "reader:reader:short",
    ],
)
def test_invalid_auth_users_configuration_is_rejected(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_auth_users(raw)


def test_jwt_configuration_requires_a_long_secret() -> None:
    with pytest.raises(ValueError):
        validate_runtime_settings(
            Settings(auth_users=AUTH_USERS, jwt_secret="too-short"),
        )
    with pytest.raises(ValueError):
        validate_runtime_settings(
            Settings(auth_users=AUTH_USERS, jwt_secret=JWT_SECRET, jwt_expiration_minutes=0),
        )
    with pytest.raises(ValueError):
        validate_runtime_settings(
            Settings(auth_users=AUTH_USERS, jwt_secret=JWT_SECRET, refresh_token_expiration_days=0),
        )


def test_cors_rejects_defaults() -> None:
    with pytest.raises(ValueError):
        get_cors_origins("*")
    assert get_cors_origins("http://localhost:5173") == ["http://localhost:5173"]
