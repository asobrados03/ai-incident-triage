import asyncio
from collections.abc import Iterator
from uuid import uuid4

import httpx
import pytest
from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.analyzer import AnalyzerProviderUnavailableError, AnalyzerTimeoutError
from app.config import Settings, validate_runtime_settings
from app.database import Base, get_db_session
from app.main import app
from app.main import get_incident_service
from app.repository import IncidentRepository
from app.service import IncidentService


class SyncASGIClient:
    def __init__(self) -> None:
        self._transport = httpx.ASGITransport(app=app)

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        async def send() -> httpx.Response:
            async with httpx.AsyncClient(
                transport=self._transport,
                base_url="http://testserver",
            ) as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(send())

    def get(self, url: str, **kwargs) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def patch(self, url: str, **kwargs) -> httpx.Response:
        return self.request("PATCH", url, **kwargs)


@pytest.fixture
def client(tmp_path) -> Iterator[SyncASGIClient]:
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
        yield SyncASGIClient()
    finally:
        app.dependency_overrides.clear()
        database_engine.dispose()


def test_health(client: SyncASGIClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "analyzer_backend": "fake"}


def test_health_does_not_require_analyzer_provider(client: SyncASGIClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["analyzer_backend"] == "fake"


@pytest.mark.parametrize(
    "settings",
    [
        Settings(analyzer_backend="unsupported"),
        Settings(
            analyzer_backend="ollama",
            ollama_base_url="not-a-url",
        ),
        Settings(
            analyzer_backend="ollama",
            ollama_model=" ",
        ),
        Settings(
            analyzer_backend="ollama",
            ollama_timeout_seconds=0,
        ),
    ],
)
def test_invalid_runtime_settings_are_rejected(settings: Settings) -> None:
    with pytest.raises(ValueError):
        validate_runtime_settings(settings)


def test_create_incident_with_optional_fields(client: SyncASGIClient) -> None:
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


def test_incident_survives_new_database_session(client: SyncASGIClient) -> None:
    created = client.post(
        "/incidents",
        json={"title": "Fallo persistente", "description": "Descripción."},
    )
    incident_id = created.json()["id"]

    # Cada request crea y cierra una nueva sesión contra la misma SQLite temporal.
    response = client.get(f"/incidents/{incident_id}")

    assert response.status_code == 200
    assert response.json()["id"] == incident_id


def test_get_existing_incident(client: SyncASGIClient) -> None:
    created = client.post(
        "/incidents",
        json={"title": "Fallo", "description": "Descripción del fallo."},
    )
    incident_id = created.json()["id"]

    response = client.get(f"/incidents/{incident_id}")

    assert response.status_code == 200
    assert response.json()["id"] == incident_id


def test_create_incident_validates_required_and_length_fields(
    client: SyncASGIClient,
) -> None:
    response = client.post(
        "/incidents",
        json={"title": "", "description": "x" * 5001},
    )

    assert response.status_code == 422


def test_create_incident_rejects_too_many_components(client: SyncASGIClient) -> None:
    response = client.post(
        "/incidents",
        json={
            "title": "Fallo",
            "description": "Descripción.",
            "components": [f"component-{index}" for index in range(21)],
        },
    )

    assert response.status_code == 422


def test_create_incident_rejects_unknown_fields(client: SyncASGIClient) -> None:
    response = client.post(
        "/incidents",
        json={
            "title": "Fallo",
            "description": "Descripción del fallo.",
            "priority": "high",
        },
    )

    assert response.status_code == 422


def test_get_missing_incident_returns_404(client: SyncASGIClient) -> None:
    response = client.get(f"/incidents/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Incident not found"}


def test_analyze_incident_returns_structured_triage(client: SyncASGIClient) -> None:
    created = client.post(
        "/incidents",
        json={
            "title": "La pantalla está lenta",
            "description": "El rendimiento del panel es muy lento.",
            "steps_to_reproduce": "Abrir el panel.",
            "environment": "Producción",
            "components": ["frontend"],
        },
    )
    incident_id = created.json()["id"]

    response = client.post(f"/incidents/{incident_id}/analysis")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "analyzed"
    assert body["triage"]["category"] == "performance"
    assert body["triage"]["severity"] == "high"
    assert body["triage"]["priority"] == "high"
    assert body["triage"]["affected_components"] == ["frontend"]
    assert body["triage"]["missing_information"] == []
    assert body["triage"]["confidence"] == "high"
    assert body["triage"]["summary"]
    assert body["triage"]["justification"]
    assert body["triage"]["id"]
    assert body["triage"]["created_at"]


def test_analysis_persists_and_is_returned_by_get(client: SyncASGIClient) -> None:
    created = client.post(
        "/incidents",
        json={"title": "Fallo", "description": "No funciona."},
    )
    incident_id = created.json()["id"]

    analyzed = client.post(f"/incidents/{incident_id}/analysis")
    fetched = client.get(f"/incidents/{incident_id}")

    assert analyzed.status_code == 200
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "analyzed"
    assert fetched.json()["triage"] == analyzed.json()["triage"]


def test_post_get_and_analysis_work_across_distinct_sessions(
    client: SyncASGIClient,
) -> None:
    created = client.post(
        "/incidents",
        json={"title": "Flujo completo", "description": "Debe persistir."},
    )
    incident_id = created.json()["id"]

    fetched = client.get(f"/incidents/{incident_id}")
    analyzed = client.post(f"/incidents/{incident_id}/analysis")

    assert created.status_code == 201
    assert fetched.status_code == 200
    assert analyzed.status_code == 200
    assert fetched.json()["id"] == incident_id
    assert analyzed.json()["id"] == incident_id
    assert analyzed.json()["status"] == "analyzed"


def test_analyze_missing_incident_returns_404(client: SyncASGIClient) -> None:
    response = client.post(f"/incidents/{uuid4()}/analysis")

    assert response.status_code == 404
    assert response.json() == {"detail": "Incident not found"}


def test_analyze_already_analyzed_incident_returns_409(client: SyncASGIClient) -> None:
    created = client.post(
        "/incidents",
        json={"title": "Fallo", "description": "No funciona."},
    )
    incident_id = created.json()["id"]

    first = client.post(f"/incidents/{incident_id}/analysis")
    second = client.post(f"/incidents/{incident_id}/analysis")

    assert first.status_code == 200
    assert second.status_code == 409
    assert "analyzed" in second.json()["detail"]


def test_analyzer_provider_error_returns_502_and_marks_failed(
    client: SyncASGIClient,
) -> None:
    class UnavailableAnalyzer:
        def analyze(self, incident):
            raise AnalyzerProviderUnavailableError("Ollama unavailable")

    def get_failing_service(
        session: Session = Depends(get_db_session),
    ) -> IncidentService:
        return IncidentService(IncidentRepository(session), UnavailableAnalyzer())

    app.dependency_overrides[get_incident_service] = get_failing_service

    created = client.post(
        "/incidents",
        json={"title": "Fallo", "description": "No funciona."},
    )
    incident_id = created.json()["id"]

    response = client.post(f"/incidents/{incident_id}/analysis")
    fetched = client.get(f"/incidents/{incident_id}")

    assert response.status_code == 502
    assert response.json()["detail"] == "Analyzer provider unavailable"
    assert "ollama" not in response.json()["detail"].lower()
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "analysis_failed"


def test_analyzer_timeout_returns_504_and_marks_failed(
    client: SyncASGIClient,
) -> None:
    class TimeoutAnalyzer:
        def analyze(self, incident):
            raise AnalyzerTimeoutError("Ollama timed out")

    def get_timeout_service(
        session: Session = Depends(get_db_session),
    ) -> IncidentService:
        return IncidentService(IncidentRepository(session), TimeoutAnalyzer())

    app.dependency_overrides[get_incident_service] = get_timeout_service

    created = client.post(
        "/incidents",
        json={"title": "Fallo", "description": "No funciona."},
    )
    incident_id = created.json()["id"]

    response = client.post(f"/incidents/{incident_id}/analysis")
    fetched = client.get(f"/incidents/{incident_id}")

    assert response.status_code == 504
    assert response.json()["detail"] == "Analyzer provider timed out"
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "analysis_failed"


def create_analyzed_incident(client: SyncASGIClient) -> str:
    created = client.post(
        "/incidents",
        json={
            "title": "Fallo",
            "description": "No funciona.",
            "steps_to_reproduce": "Abrir la pantalla.",
            "environment": "Producción",
            "components": ["frontend"],
        },
    )
    incident_id = created.json()["id"]
    analyzed = client.post(f"/incidents/{incident_id}/analysis")
    assert analyzed.status_code == 200
    return incident_id


def test_review_accepts_ai_result_without_field_changes(client: SyncASGIClient) -> None:
    incident_id = create_analyzed_incident(client)

    response = client.patch(
        f"/incidents/{incident_id}/triage",
        json={"review_comment": "Revisado y aceptado."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "reviewed"
    assert body["triage"]["category"] == "bug"
    assert body["triage"]["review"]["reviewed"] is True
    assert body["triage"]["review"]["source"] == "human"
    assert body["triage"]["review"]["review_comment"] == "Revisado y aceptado."
    assert body["triage"]["review"]["final"]["category"] == "bug"


def test_review_applies_partial_correction_and_preserves_original(client: SyncASGIClient) -> None:
    incident_id = create_analyzed_incident(client)

    response = client.patch(
        f"/incidents/{incident_id}/triage",
        json={
            "severity": "critical",
            "priority": "urgent",
            "review_comment": "Impacto confirmado por soporte.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "reviewed"
    assert body["triage"]["severity"] == "medium"
    assert body["triage"]["priority"] == "medium"
    assert body["triage"]["review"]["final"]["severity"] == "critical"
    assert body["triage"]["review"]["final"]["priority"] == "urgent"


def test_review_rejects_empty_request(client: SyncASGIClient) -> None:
    incident_id = create_analyzed_incident(client)

    response = client.patch(f"/incidents/{incident_id}/triage", json={})

    assert response.status_code == 422


def test_review_without_analysis_returns_409(client: SyncASGIClient) -> None:
    created = client.post(
        "/incidents",
        json={"title": "Fallo", "description": "No funciona."},
    )

    response = client.patch(
        f"/incidents/{created.json()['id']}/triage",
        json={"severity": "high"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Incident has no triage result"


def test_review_missing_incident_returns_404(client: SyncASGIClient) -> None:
    response = client.patch(
        f"/incidents/{uuid4()}/triage",
        json={"severity": "high"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Incident not found"}


def test_duplicate_review_returns_409(client: SyncASGIClient) -> None:
    incident_id = create_analyzed_incident(client)
    first = client.patch(
        f"/incidents/{incident_id}/triage",
        json={"review_comment": "Aceptado."},
    )
    second = client.patch(
        f"/incidents/{incident_id}/triage",
        json={"severity": "critical"},
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"] == "Incident has already been reviewed"
