import pytest

from app.auth import Principal, Role, parse_api_keys
from app.infrastructure.config import Settings


VALID_READER_KEY = "reader-key-0123456789"
VALID_ADMIN_KEY = "admin-key-0123456789"


def test_empty_api_keys_disable_authentication() -> None:
    store = parse_api_keys("")

    assert not store.enabled
    assert store.authenticate(None) == Principal.anonymous()


def test_parse_api_keys_authenticates_each_role() -> None:
    store = parse_api_keys(
        f"reader:reader:{VALID_READER_KEY},admin:admin:{VALID_ADMIN_KEY}",
    )

    assert store.enabled
    assert store.authenticate(VALID_READER_KEY) == Principal(
        name="reader",
        role=Role.READER,
    )
    assert store.authenticate(VALID_ADMIN_KEY) == Principal(
        name="admin",
        role=Role.ADMIN,
    )
    assert store.authenticate(None) is None
    assert store.authenticate("wrong-key-0123456789") is None


def test_settings_repr_does_not_expose_api_keys() -> None:
    settings = Settings(api_keys=f"admin:admin:{VALID_ADMIN_KEY}")

    assert VALID_ADMIN_KEY not in repr(settings)
    assert VALID_ADMIN_KEY not in str(settings)


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
        "short:reader:abc",
        ":reader:0123456789abcdef",
        (
            "duplicate:reader:0123456789abcdef,"
            "duplicate:admin:fedcba9876543210"
        ),
        (
            "first:reader:0123456789abcdef,"
            "second:writer:0123456789abcdef"
        ),
        "trailing:reader:0123456789abcdef,",
    ],
)
def test_invalid_api_keys_configuration_is_rejected(raw: str) -> None:
    with pytest.raises(ValueError) as error:
        parse_api_keys(raw)

    assert "0123456789abcdef" not in str(error.value)
    assert "fedcba9876543210" not in str(error.value)
