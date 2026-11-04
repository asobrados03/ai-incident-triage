from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.infrastructure.config import get_settings


class Base(DeclarativeBase):
    pass


def create_database_engine(database_url: str | None = None):
    url = database_url or get_settings().database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


engine = create_database_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def create_tables(database_engine=engine) -> None:
    # Import local para registrar los modelos en Base.metadata sin ciclos.
    from backend.infrastructure import orm_models  # noqa: F401

    Base.metadata.create_all(bind=database_engine)
    apply_lightweight_migrations(database_engine)


def apply_lightweight_migrations(database_engine=engine) -> None:
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
                    "ALTER TABLE triage_reviews "
                    "ADD COLUMN review_checklist JSON",
                ),
            )


def get_db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
