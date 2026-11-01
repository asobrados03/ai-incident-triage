import asyncio
from collections.abc import Iterator

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.config import Settings, get_settings
from app.infrastructure.database import Base, get_db_session
from app.main import app


READER_KEY = "reader-key-0123456789"
WRITER_KEY = "writer-key-0123456789"
ADMIN_KEY = "admin-key-0123456789"
API_KEYS = (
    f"reader:reader:{READER_KEY},"
    f"writer:writer:{WRITER_KEY},"
    f"admin:admin:{ADMIN_KEY}"
)


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
def secure_client(tmp_path) -> Iterator[SyncASGIClient]:
    database_engine = create_engine(
        f"sqlite:///{tmp_path / 'secure.db'}",
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

    test_settings = Settings(api_keys=API_KEYS)
    app.dependency_overrides[get_db_session] = get_test_session
    app.dependency_overrides[get_settings] = lambda: test_settings
    try:
        yield SyncASGIClient()
    finally:
        app.dependency_overrides.clear()
        database_engine.dispose()


def auth(key: str) -> dict[str, str]:
    return {"X-API-Key": key}


def incident_payload() -> dict:
    return {
        "title": "Título confidencial",
        "description": "Descripción con datos sensibles del cliente.",
        "components": ["frontend"],
    }


def create_incident(
    client: SyncASGIClient,
    key: str = WRITER_KEY,
) -> str:
    response = client.post(
        "/incidents",
        json=incident_payload(),
        headers=auth(key),
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_health_remains_public_with_authentication_enabled(
    secure_client: SyncASGIClient,
) -> None:
    response = secure_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "analyzer_backend": "fake"}


def test_missing_api_key_returns_401_without_exposing_secrets(
    secure_client: SyncASGIClient,
) -> None:
    response = secure_client.post("/incidents", json=incident_payload())

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing API key"}
    assert response.headers["www-authenticate"] == "X-API-Key"
    assert WRITER_KEY not in response.text


def test_invalid_api_key_returns_401_without_echoing_the_key(
    secure_client: SyncASGIClient,
) -> None:
    invalid_key = "wrong-key-0123456789"
    response = secure_client.post(
        "/incidents",
        json=incident_payload(),
        headers=auth(invalid_key),
    )

    assert response.status_code == 401
    assert invalid_key not in response.text


def test_reader_can_read_but_cannot_write(
    secure_client: SyncASGIClient,
) -> None:
    incident_id = create_incident(secure_client)

    fetched = secure_client.get(
        f"/incidents/{incident_id}",
        headers=auth(READER_KEY),
    )
    denied = secure_client.post(
        "/incidents",
        json=incident_payload(),
        headers=auth(READER_KEY),
    )

    assert fetched.status_code == 200
    assert denied.status_code == 403
    assert denied.json() == {"detail": "Insufficient permissions"}


def test_writer_can_create_analyze_and_review_but_not_admin_routes(
    secure_client: SyncASGIClient,
) -> None:
    incident_id = create_incident(secure_client, WRITER_KEY)

    analyzed = secure_client.post(
        f"/incidents/{incident_id}/analysis",
        headers=auth(WRITER_KEY),
    )
    reviewed = secure_client.patch(
        f"/incidents/{incident_id}/triage",
        json={"review_comment": "Revisado."},
        headers=auth(WRITER_KEY),
    )
    audit_denied = secure_client.get("/audit", headers=auth(WRITER_KEY))
    retention_denied = secure_client.post(
        "/admin/retention",
        json={"dry_run": True},
        headers=auth(WRITER_KEY),
    )

    assert analyzed.status_code == 200
    assert reviewed.status_code == 200
    assert audit_denied.status_code == 403
    assert retention_denied.status_code == 403


def test_admin_can_list_audit_events_without_sensitive_content(
    secure_client: SyncASGIClient,
) -> None:
    incident_id = create_incident(secure_client, WRITER_KEY)
    secure_client.post(
        f"/incidents/{incident_id}/analysis",
        headers=auth(WRITER_KEY),
    )

    response = secure_client.get("/audit", headers=auth(ADMIN_KEY))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 2
    actions = {item["action"] for item in body["items"]}
    assert {"incident.create", "incident.analyze"} <= actions
    for item in body["items"]:
        assert item["actor"] == "writer"
        assert item["role"] == "writer"
        assert item["resource_type"] == "incident"
        assert item["resource_id"] == incident_id
        assert set(item["details"]) <= {
            "status",
            "duration_ms",
            "changed_fields",
            "has_comment",
            "error_type",
        }
    assert "confidencial" not in response.text
    assert "sensibles" not in response.text
    assert WRITER_KEY not in response.text
    assert ADMIN_KEY not in response.text

    filtered = secure_client.get(
        "/audit",
        params={"action": "incident.create"},
        headers=auth(ADMIN_KEY),
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["action"] == "incident.create"


def test_admin_retention_dry_run_is_audited(
    secure_client: SyncASGIClient,
) -> None:
    response = secure_client.post(
        "/admin/retention",
        json={"dry_run": True},
        headers=auth(ADMIN_KEY),
    )

    assert response.status_code == 200
    assert response.json()["dry_run"] is True
    assert response.json()["incidents_matched"] == 0

    audit = secure_client.get(
        "/audit",
        params={"action": "retention.run"},
        headers=auth(ADMIN_KEY),
    )
    assert audit.status_code == 200
    assert audit.json()["total"] == 1
    entry = audit.json()["items"][0]
    assert entry["actor"] == "admin"
    assert entry["role"] == "admin"
    assert entry["details"]["dry_run"] is True


def test_retention_rejects_non_positive_days(
    secure_client: SyncASGIClient,
) -> None:
    response = secure_client.post(
        "/admin/retention",
        json={"dry_run": True, "incidents_days": 0},
        headers=auth(ADMIN_KEY),
    )

    assert response.status_code == 422
