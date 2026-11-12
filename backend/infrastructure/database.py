from collections.abc import Generator
from typing import Any

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.infrastructure.config import get_settings


class Base(DeclarativeBase):
    pass


def _enable_sqlite_foreign_keys(
    dbapi_connection: Any,
    connection_record: Any,
) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_database_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().database_url
    is_sqlite = url.startswith("sqlite")
    connect_args = {"check_same_thread": False} if is_sqlite else {}
    database_engine = create_engine(url, connect_args=connect_args)
    if is_sqlite:
        event.listen(database_engine, "connect", _enable_sqlite_foreign_keys)
    return database_engine


engine = create_database_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def create_tables(database_engine: Engine = engine) -> None:
    # Import local para registrar los modelos en Base.metadata sin ciclos.
    from backend.infrastructure import orm_models  # noqa: F401

    Base.metadata.create_all(bind=database_engine)
    apply_lightweight_migrations(database_engine)


def apply_lightweight_migrations(database_engine: Engine = engine) -> None:
    """Añade columnas nuevas a bases SQLite ya existentes.

    El MVP no tiene migraciones versionadas; ``create_all`` no altera tablas
    existentes. Esta función cubre únicamente las columnas aditivas conocidas.
    """
    inspector = inspect(database_engine)
    if "triage_reviews" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("triage_reviews")}
    if "review_checklist" not in columns:
        with database_engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE triage_reviews ADD COLUMN review_checklist JSON",
                ),
            )


def get_db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
