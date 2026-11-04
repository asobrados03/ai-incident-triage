import asyncio
from collections.abc import Iterator

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.auth import BootstrapUser, Role
from backend.infrastructure.config import Settings, get_settings
from backend.infrastructure.database import Base, get_db_session
from backend.infrastructure.repositories import UserRepository
from backend.main import app
from backend.services.users import UserService


PASSWORDS = {
    "reader": "reader-password-0123456789",
    "writer": "writer-password-0123456789",
    "admin": "admin-password-0123456789",
}
AUTH_USERS = ",".join(
    f"{name}:{name}:{password}" for name, password in PASSWORDS.items()
)
JWT_SECRET = "test-jwt-secret-that-is-long-enough-123456"


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

    def delete(self, url: str, **kwargs) -> httpx.Response:
        return self.request("DELETE", url, **kwargs)


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

    test_settings = Settings(
        auth_users=AUTH_USERS,
        jwt_secret=JWT_SECRET,
    )
    seed_session = test_session_factory()
    try:
        UserService(UserRepository(seed_session)).bootstrap(
            tuple(
                BootstrapUser(
                    username=name,
                    role=Role(name),
                    password=password,
                )
                for name, password in PASSWORDS.items()
            ),
        )
    finally:
        seed_session.close()
    app.dependency_overrides[get_db_session] = get_test_session
    app.dependency_overrides[get_settings] = lambda: test_settings
    try:
        yield SyncASGIClient()
    finally:
        app.dependency_overrides.clear()
        database_engine.dispose()


def auth(client: SyncASGIClient, username: str) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"username": username, "password": PASSWORDS[username]},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def incident_payload() -> dict:
    return {
        "title": "Título confidencial",
        "description": "Descripción con datos sensibles del cliente.",
        "components": ["frontend"],
    }


def create_incident(
    client: SyncASGIClient,
    username: str = "writer",
) -> str:
    response = client.post(
        "/incidents",
        json=incident_payload(),
        headers=auth(client, username),
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_health_remains_public_with_authentication_enabled(
    secure_client: SyncASGIClient,
) -> None:
    response = secure_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "analyzer_backend": "fake"}


def test_login_issues_bearer_token(secure_client: SyncASGIClient) -> None:
    response = secure_client.post(
        "/auth/login",
        json={"username": "writer", "password": PASSWORDS["writer"]},
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"]


def test_missing_token_returns_401_without_exposing_secrets(
    secure_client: SyncASGIClient,
) -> None:
    response = secure_client.post("/incidents", json=incident_payload())

    assert response.status_code == 401
    assert response.json() == {"detail": "Missing or invalid bearer token"}
    assert response.headers["www-authenticate"] == "Bearer"
    assert PASSWORDS["writer"] not in response.text


def test_invalid_token_returns_401(secure_client: SyncASGIClient) -> None:
    response = secure_client.post(
        "/incidents",
        json=incident_payload(),
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Missing or invalid bearer token"}


def test_invalid_login_returns_401(secure_client: SyncASGIClient) -> None:
    response = secure_client.post(
        "/auth/login",
        json={"username": "writer", "password": "wrong-password"},
    )

    assert response.status_code == 401


def test_reader_can_read_but_cannot_write(
    secure_client: SyncASGIClient,
) -> None:
    incident_id = create_incident(secure_client)

    fetched = secure_client.get(
        f"/incidents/{incident_id}",
        headers=auth(secure_client, "reader"),
    )
    denied = secure_client.post(
        "/incidents",
        json=incident_payload(),
        headers=auth(secure_client, "reader"),
    )

    assert fetched.status_code == 200
    assert denied.status_code == 403
    assert denied.json() == {"detail": "Insufficient permissions"}


def test_writer_can_create_analyze_and_review_but_not_admin_routes(
    secure_client: SyncASGIClient,
) -> None:
    incident_id = create_incident(secure_client, "writer")
    writer_auth = auth(secure_client, "writer")

    analyzed = secure_client.post(
        f"/incidents/{incident_id}/analysis",
        headers=writer_auth,
    )
    reviewed = secure_client.patch(
        f"/incidents/{incident_id}/triage",
        json={"review_comment": "Revisado."},
        headers=writer_auth,
    )
    audit_denied = secure_client.get("/audit", headers=writer_auth)
    retention_denied = secure_client.post(
        "/admin/retention",
        json={"dry_run": True},
        headers=writer_auth,
    )

    assert analyzed.status_code == 200
    assert reviewed.status_code == 200
    assert audit_denied.status_code == 403
    assert retention_denied.status_code == 403


def test_admin_can_list_audit_events_without_sensitive_content(
    secure_client: SyncASGIClient,
) -> None:
    incident_id = create_incident(secure_client, "writer")
    secure_client.post(
        f"/incidents/{incident_id}/analysis",
        headers=auth(secure_client, "writer"),
    )

    response = secure_client.get("/audit", headers=auth(secure_client, "admin"))

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
            "checklist_items",
            "error_type",
        }
    assert "confidencial" not in response.text
    assert "sensibles" not in response.text
    assert PASSWORDS["writer"] not in response.text

    filtered = secure_client.get(
        "/audit",
        params={"action": "incident.create"},
        headers=auth(secure_client, "admin"),
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
        headers=auth(secure_client, "admin"),
    )

    assert response.status_code == 200
    assert response.json()["dry_run"] is True
    assert response.json()["incidents_matched"] == 0

    audit = secure_client.get(
        "/audit",
        params={"action": "retention.run"},
        headers=auth(secure_client, "admin"),
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
        headers=auth(secure_client, "admin"),
    )

    assert response.status_code == 422


def find_user_id(client: SyncASGIClient, username: str) -> str:
    response = client.get("/users", headers=auth(client, "admin"))
    assert response.status_code == 200
    return next(
        item["id"]
        for item in response.json()["items"]
        if item["username"] == username
    )


def test_auth_me_reports_the_authenticated_role(
    secure_client: SyncASGIClient,
) -> None:
    response = secure_client.get("/auth/me", headers=auth(secure_client, "reader"))

    assert response.status_code == 200
    assert response.json() == {
        "name": "reader",
        "role": "reader",
        "authenticated": True,
    }


def test_auth_me_requires_a_token_when_auth_is_enabled(
    secure_client: SyncASGIClient,
) -> None:
    response = secure_client.get("/auth/me")

    assert response.status_code == 401


def test_admin_can_create_and_list_users_without_exposing_hashes(
    secure_client: SyncASGIClient,
) -> None:
    admin_auth = auth(secure_client, "admin")
    created = secure_client.post(
        "/users",
        json={
            "username": "nuevo.soporte",
            "password": "nuevo-password-0123456789",
            "role": "writer",
        },
        headers=admin_auth,
    )

    assert created.status_code == 201
    body = created.json()
    assert body["username"] == "nuevo.soporte"
    assert body["role"] == "writer"
    assert body["active"] is True
    assert "password" not in body
    assert "hash" not in created.text

    listed = secure_client.get("/users", headers=admin_auth)
    assert listed.status_code == 200
    assert listed.json()["total"] == 4
    assert "nuevo.soporte" in {
        item["username"] for item in listed.json()["items"]
    }
    assert "argon2" not in listed.text

    login = secure_client.post(
        "/auth/login",
        json={
            "username": "nuevo.soporte",
            "password": "nuevo-password-0123456789",
        },
    )
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "writer"


def test_user_management_validates_duplicates_and_passwords(
    secure_client: SyncASGIClient,
) -> None:
    admin_auth = auth(secure_client, "admin")
    duplicate = secure_client.post(
        "/users",
        json={
            "username": "reader",
            "password": "another-password-0123456789",
            "role": "reader",
        },
        headers=admin_auth,
    )
    short_password = secure_client.post(
        "/users",
        json={"username": "corto", "password": "short", "role": "reader"},
        headers=admin_auth,
    )

    assert duplicate.status_code == 409
    assert short_password.status_code == 422


def test_only_admins_can_manage_users(secure_client: SyncASGIClient) -> None:
    denied = secure_client.get("/users", headers=auth(secure_client, "reader"))
    created = secure_client.post(
        "/users",
        json={
            "username": "otro",
            "password": "otro-password-0123456789",
            "role": "reader",
        },
        headers=auth(secure_client, "writer"),
    )

    assert denied.status_code == 403
    assert created.status_code == 403


def test_password_change_revokes_previous_tokens(
    secure_client: SyncASGIClient,
) -> None:
    reader_id = find_user_id(secure_client, "reader")
    old_token = auth(secure_client, "reader")
    changed = secure_client.patch(
        f"/users/{reader_id}",
        json={"password": "reader-new-password-0123456789"},
        headers=auth(secure_client, "admin"),
    )

    assert changed.status_code == 200
    rejected = secure_client.get("/auth/me", headers=old_token)
    assert rejected.status_code == 401

    old_login = secure_client.post(
        "/auth/login",
        json={"username": "reader", "password": PASSWORDS["reader"]},
    )
    new_login = secure_client.post(
        "/auth/login",
        json={
            "username": "reader",
            "password": "reader-new-password-0123456789",
        },
    )
    assert old_login.status_code == 401
    assert new_login.status_code == 200


def test_deactivation_revokes_access(
    secure_client: SyncASGIClient,
) -> None:
    admin_auth = auth(secure_client, "admin")
    writer_id = find_user_id(secure_client, "writer")
    writer_token = auth(secure_client, "writer")

    deactivated = secure_client.delete(
        f"/users/{writer_id}",
        headers=admin_auth,
    )

    assert deactivated.status_code == 200
    assert deactivated.json()["active"] is False
    assert secure_client.get("/auth/me", headers=writer_token).status_code == 401
    assert secure_client.post(
        "/auth/login",
        json={"username": "writer", "password": PASSWORDS["writer"]},
    ).status_code == 401


def test_last_active_admin_cannot_be_demoted_or_deactivated(
    secure_client: SyncASGIClient,
) -> None:
    admin_id = find_user_id(secure_client, "admin")
    admin_auth = auth(secure_client, "admin")

    demoted = secure_client.patch(
        f"/users/{admin_id}",
        json={"role": "reader"},
        headers=admin_auth,
    )
    deactivated = secure_client.delete(
        f"/users/{admin_id}",
        headers=admin_auth,
    )

    assert demoted.status_code == 409
    assert deactivated.status_code == 409


def test_created_user_can_write_according_to_role(
    secure_client: SyncASGIClient,
) -> None:
    admin_auth = auth(secure_client, "admin")
    secure_client.post(
        "/users",
        json={
            "username": "triage.writer",
            "password": "writer-password-0123456789",
            "role": "writer",
        },
        headers=admin_auth,
    )
    login = secure_client.post(
        "/auth/login",
        json={
            "username": "triage.writer",
            "password": "writer-password-0123456789",
        },
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    created = secure_client.post(
        "/incidents",
        json=incident_payload(),
        headers=headers,
    )
    audit_denied = secure_client.get("/audit", headers=headers)

    assert created.status_code == 201
    assert audit_denied.status_code == 403


def test_user_actions_are_audited_without_secrets(
    secure_client: SyncASGIClient,
) -> None:
    admin_auth = auth(secure_client, "admin")
    secure_client.post(
        "/users",
        json={
            "username": "auditado",
            "password": "auditado-password-0123456789",
            "role": "reader",
        },
        headers=admin_auth,
    )

    audit = secure_client.get(
        "/audit",
        params={"action": "user.create"},
        headers=admin_auth,
    )

    assert audit.status_code == 200
    assert audit.json()["total"] == 1
    assert audit.json()["items"][0]["resource_type"] == "user"
    assert "auditado-password" not in audit.text
    assert "argon2" not in audit.text
