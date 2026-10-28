from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db_session
from app.main import app


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    database_engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(database_engine)
    test_session_factory = sessionmaker(
        bind=database_engine,
        autocommit=False,
        autoflush=False,
    )

    def get_test_session() -> Iterator[Session]:
        session = test_session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = get_test_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        database_engine.dispose()


def test_health(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_incident_with_optional_fields(client: TestClient) -> None:
    payload = {
        "title": "No se puede iniciar sesión",
        "description": "El formulario devuelve un error inesperado.",
        "steps_to_reproduce": "Abrir la pantalla de acceso y enviar el formulario.",
        "expected_behavior": "Acceder al panel.",
        "actual_behavior": "Se muestra un error.",
        "environment": "Producción",
        "components": ["auth", "frontend"],
    }

    response = client.post("/incidents", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == payload["title"]
    assert body["components"] == payload["components"]
    assert body["status"] == "created"
    assert "id" in body
    assert "created_at" in body


def test_incident_survives_new_database_session(client: TestClient) -> None:
    created = client.post(
        "/incidents",
        json={"title": "Fallo persistente", "description": "Descripción."},
    )
    incident_id = created.json()["id"]

    # Cada request crea y cierra una nueva sesión contra la misma SQLite temporal.
    response = client.get(f"/incidents/{incident_id}")

    assert response.status_code == 200
    assert response.json()["id"] == incident_id


def test_get_existing_incident(client: TestClient) -> None:
    created = client.post(
        "/incidents",
        json={"title": "Fallo", "description": "Descripción del fallo."},
    )
    incident_id = created.json()["id"]

    response = client.get(f"/incidents/{incident_id}")

    assert response.status_code == 200
    assert response.json()["id"] == incident_id


def test_create_incident_validates_required_and_length_fields(
    client: TestClient,
) -> None:
    response = client.post(
        "/incidents",
        json={"title": "", "description": "x" * 5001},
    )

    assert response.status_code == 422


def test_create_incident_rejects_unknown_fields(client: TestClient) -> None:
    response = client.post(
        "/incidents",
        json={
            "title": "Fallo",
            "description": "Descripción del fallo.",
            "priority": "high",
        },
    )

    assert response.status_code == 422


def test_get_missing_incident_returns_404(client: TestClient) -> None:
    response = client.get(f"/incidents/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Incident not found"}
