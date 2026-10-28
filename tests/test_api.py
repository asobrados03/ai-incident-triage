from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_incident_with_optional_fields() -> None:
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


def test_get_existing_incident() -> None:
    created = client.post(
        "/incidents",
        json={"title": "Fallo", "description": "Descripción del fallo."},
    )
    incident_id = created.json()["id"]

    response = client.get(f"/incidents/{incident_id}")

    assert response.status_code == 200
    assert response.json()["id"] == incident_id


def test_create_incident_validates_required_and_length_fields() -> None:
    response = client.post(
        "/incidents",
        json={"title": "", "description": "x" * 5001},
    )

    assert response.status_code == 422


def test_create_incident_rejects_unknown_fields() -> None:
    response = client.post(
        "/incidents",
        json={
            "title": "Fallo",
            "description": "Descripción del fallo.",
            "priority": "high",
        },
    )

    assert response.status_code == 422


def test_get_missing_incident_returns_404() -> None:
    response = client.get(f"/incidents/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Incident not found"}
