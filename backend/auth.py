from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from functools import lru_cache
import hashlib
import secrets

import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import SecretStr

from backend.infrastructure.config import Settings, get_settings


class Role(StrEnum):
    READER = "reader"
    WRITER = "writer"
    ADMIN = "admin"


_ROLE_RANK = {
    Role.READER: 1,
    Role.WRITER: 2,
    Role.ADMIN: 3,
}


@dataclass(frozen=True)
class Principal:
    name: str
    role: Role
    authenticated: bool = True

    @classmethod
    def anonymous(cls) -> "Principal":
        return cls(name="anonymous", role=Role.ADMIN, authenticated=False)

    @classmethod
    def system(cls) -> "Principal":
        return cls(name="system", role=Role.ADMIN, authenticated=False)

    def has_at_least(self, required: Role) -> bool:
        return _ROLE_RANK[self.role] >= _ROLE_RANK[required]


@dataclass(frozen=True)
class _AuthUser:
    name: str
    role: Role
    password_digest: bytes


class AuthUserStore:
    def __init__(self, users: list[_AuthUser]) -> None:
        self._users = tuple(users)

    @property
    def enabled(self) -> bool:
        return bool(self._users)

    def authenticate(self, username: str, password: str) -> Principal | None:
        password_digest = hashlib.sha256(password.encode("utf-8")).digest()
        for user in self._users:
            if user.name == username and secrets.compare_digest(
                user.password_digest,
                password_digest,
            ):
                return Principal(name=user.name, role=user.role)
        return None


def _raw_secret(raw: str | SecretStr | None) -> str:
    if isinstance(raw, SecretStr):
        return raw.get_secret_value()
    return raw or ""


def parse_auth_users(raw: str | SecretStr | None) -> AuthUserStore:
    """Parse AUTH_USERS as ``name:role:password`` entries."""
    raw_value = _raw_secret(raw)
    if not raw_value.strip():
        return AuthUserStore([])

    users: list[_AuthUser] = []
    names: set[str] = set()
    for index, raw_entry in enumerate(raw_value.split(","), start=1):
        entry = raw_entry.strip()
        parts = entry.split(":", 2)
        if len(parts) != 3:
            raise ValueError("AUTH_USERS entries must use name:role:password format")
        name, raw_role, password = (part.strip() for part in parts)
        if not name or not password:
            raise ValueError(f"AUTH_USERS entry {index} has empty fields")
        if name in names:
            raise ValueError("AUTH_USERS contains a duplicate name")
        try:
            role = Role(raw_role.lower())
        except ValueError as error:
            raise ValueError(f"AUTH_USERS entry {index} has an invalid role") from error
        names.add(name)
        users.append(
            _AuthUser(
                name=name,
                role=role,
                password_digest=hashlib.sha256(password.encode("utf-8")).digest(),
            ),
        )
    return AuthUserStore(users)


@lru_cache(maxsize=8)
def _build_auth_user_store(raw: str) -> AuthUserStore:
    return parse_auth_users(raw)


def get_auth_user_store(raw: str | SecretStr | None) -> AuthUserStore:
    return _build_auth_user_store(_raw_secret(raw))


def create_access_token(principal: Principal, settings: Settings) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_expiration_minutes,
    )
    return jwt.encode(
        {
            "sub": principal.name,
            "role": principal.role.value,
            "exp": expires_at,
        },
        _raw_secret(settings.jwt_secret),
        algorithm="HS256",
    )


bearer_scheme = HTTPBearer(auto_error=False)


def get_principal(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> Principal:
    store = get_auth_user_store(settings.auth_users)
    if not store.enabled:
        return Principal.anonymous()
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(
            credentials.credentials,
            _raw_secret(settings.jwt_secret),
            algorithms=["HS256"],
        )
        principal = Principal(
            name=str(payload["sub"]),
            role=Role(payload["role"]),
        )
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    return principal


def require_role(required: Role):
    def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.has_at_least(required):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return principal

    return dependency
