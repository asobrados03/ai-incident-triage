import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from backend.auth import (
    BootstrapUser,
    Principal,
    Role,
    hash_password,
    verify_password,
)
from backend.infrastructure.database import Base, apply_lightweight_migrations
from backend.infrastructure.repositories import AuditRepository, UserRepository
from backend.api.schemas import UserCreate, UserUpdate
from backend.services.users import UserConflictError, UserService


ADMIN_PASSWORD = "admin-password-0123456789"
READER_PASSWORD = "reader-password-0123456789"


@pytest.fixture
def session(tmp_path):
    database_engine = create_engine(
        f"sqlite:///{tmp_path / 'users.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(database_engine)
    factory = sessionmaker(
        bind=database_engine,
        autocommit=False,
        autoflush=False,
    )
    with factory() as db_session:
        yield db_session
    database_engine.dispose()


def make_service(session: Session) -> UserService:
    return UserService(UserRepository(session), AuditRepository(session))


def test_bootstrap_is_idempotent_and_keeps_existing_credentials(
    session: Session,
) -> None:
    service = make_service(session)
    seed = (
        BootstrapUser(
            username="admin",
            role=Role.ADMIN,
            password=ADMIN_PASSWORD,
        ),
    )

    assert service.bootstrap(seed) == 1
    assert service.bootstrap(seed) == 0

    record = UserRepository(session).get_by_username("admin")
    assert record is not None
    assert record.role == "admin"
    assert verify_password(ADMIN_PASSWORD, record.password_hash)
    assert "argon2" in record.password_hash


def test_login_updates_last_login_and_rejects_inactive_users(
    session: Session,
) -> None:
    service = make_service(session)
    record = UserRepository(session).create(
        username="reader",
        password_hash=hash_password(READER_PASSWORD),
        role=Role.READER,
    )

    result = service.login("reader", READER_PASSWORD)
    assert result is not None
    assert result.principal == Principal(name="reader", role=Role.READER)
    assert result.user.last_login_at is not None

    UserRepository(session).update(record, active=False)
    assert service.login("reader", READER_PASSWORD) is None


def test_login_rejects_unknown_users_and_wrong_passwords(
    session: Session,
) -> None:
    service = make_service(session)
    assert service.login("missing", READER_PASSWORD) is None

    service.create(
        UserCreate(
            username="reader",
            password=READER_PASSWORD,
            role=Role.READER,
        ),
        actor=Principal(name="admin", role=Role.ADMIN),
    )
    assert service.login("reader", "wrong-password") is None


def test_cannot_create_duplicate_usernames(session: Session) -> None:
    service = make_service(session)
    admin = Principal(name="admin", role=Role.ADMIN)
    payload = UserCreate(
        username="reader",
        password=READER_PASSWORD,
        role=Role.READER,
    )

    service.create(payload, actor=admin)
    with pytest.raises(UserConflictError):
        service.create(payload, actor=admin)


def test_only_admin_can_be_target_of_admin_guards(session: Session) -> None:
    service = make_service(session)
    admin = Principal(name="root", role=Role.ADMIN)
    created = service.create(
        UserCreate(
            username="root",
            password=ADMIN_PASSWORD,
            role=Role.ADMIN,
        ),
        actor=admin,
    )

    with pytest.raises(UserConflictError):
        service.update(created.id, UserUpdate(role=Role.READER), actor=admin)
    with pytest.raises(UserConflictError):
        service.deactivate(created.id, actor=admin)


def test_lightweight_migration_adds_checklist_to_legacy_database(
    tmp_path,
) -> None:
    database_engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with database_engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE triage_reviews ("
                "id VARCHAR(36) PRIMARY KEY, "
                "review_comment VARCHAR(2000)"
                ")",
            ),
        )
        connection.execute(
            text(
                "INSERT INTO triage_reviews (id, review_comment) "
                "VALUES ('legacy', 'ok')",
            ),
        )

    apply_lightweight_migrations(database_engine)

    columns = {
        column["name"]
        for column in inspect(database_engine).get_columns("triage_reviews")
    }
    assert "review_checklist" in columns
    database_engine.dispose()
