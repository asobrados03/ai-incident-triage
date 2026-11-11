from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import SecretStr
from sqlalchemy.orm import Session

from backend.infrastructure.config import Settings, get_settings
from backend.infrastructure.database import get_db_session

if TYPE_CHECKING:
    from backend.infrastructure.orm_models import UserORM
    from backend.infrastructure.repositories import UserRepository


class Role(StrEnum):
    READER = "reader"
    WRITER = "writer"
    ADMIN = "admin"


_ROLE_RANK = {
    Role.READER: 1,
    Role.WRITER: 2,
    Role.ADMIN: 3,
}

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{3,100}$")
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 200

_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash("dummy-password-used-for-timing")


@dataclass(frozen=True)
class Principal:
    name: str
    role: Role
    authenticated: bool = True

    @classmethod
    def anonymous(cls) -> Principal:
        return cls(name="anonymous", role=Role.ADMIN, authenticated=False)

    @classmethod
    def system(cls) -> Principal:
        return cls(name="system", role=Role.ADMIN, authenticated=False)

    def has_at_least(self, required: Role) -> bool:
        return _ROLE_RANK[self.role] >= _ROLE_RANK[required]


@dataclass(frozen=True)
class BootstrapUser:
    username: str
    role: Role
    password: str


def hash_password(password: str) -> str:
    if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        raise ValueError(
            f"Password must be between {PASSWORD_MIN_LENGTH} and {PASSWORD_MAX_LENGTH} characters",
        )
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    # Verificar contra un hash dummy cuando el usuario no existe reduce la
    # diferencia de tiempo entre un usuario inexistente y una contraseña mala.
    candidate = password_hash or _DUMMY_HASH
    try:
        return _hasher.verify(candidate, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def _raw_secret(raw: str | SecretStr | None) -> str:
    if isinstance(raw, SecretStr):
        return raw.get_secret_value()
    return raw or ""


def parse_auth_users(raw: str | SecretStr | None) -> tuple[BootstrapUser, ...]:
    """Parse AUTH_USERS as ``name:role:password`` entries.

    Solo se usa para sembrar la tabla ``users`` la primera vez. Una vez que la
    base tiene usuarios, la fuente de verdad es la base de datos.
    """
    raw_value = _raw_secret(raw)
    if not raw_value.strip():
        return ()

    users: list[BootstrapUser] = []
    names: set[str] = set()
    for index, raw_entry in enumerate(raw_value.split(","), start=1):
        entry = raw_entry.strip()
        parts = entry.split(":", 2)
        if len(parts) != 3:
            raise ValueError("AUTH_USERS entries must use name:role:password format")
        name, raw_role, password = (part.strip() for part in parts)
        if not name or not password:
            raise ValueError(f"AUTH_USERS entry {index} has empty fields")
        if not USERNAME_PATTERN.fullmatch(name):
            raise ValueError(
                "AUTH_USERS usernames must use 3-100 letters, digits, '.', '_' or '-'",
            )
        if name in names:
            raise ValueError("AUTH_USERS contains a duplicate name")
        if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
            raise ValueError(
                f"AUTH_USERS entry {index} password must be between "
                f"{PASSWORD_MIN_LENGTH} and {PASSWORD_MAX_LENGTH} characters",
            )
        try:
            role = Role(raw_role.lower())
        except ValueError as error:
            raise ValueError(f"AUTH_USERS entry {index} has an invalid role") from error
        names.add(name)
        users.append(BootstrapUser(username=name, role=role, password=password))
    return tuple(users)


def jwt_secret_configured(settings: Settings) -> bool:
    return len(_raw_secret(settings.jwt_secret)) >= 32


def create_access_token(
    principal: Principal,
    settings: Settings,
    token_version: int = 0,
) -> str:
    secret = _raw_secret(settings.jwt_secret)
    if len(secret) < 32:
        raise ValueError("JWT_SECRET must be at least 32 characters")
    issued_at = datetime.now(UTC)
    expires_at = issued_at + timedelta(minutes=settings.jwt_expiration_minutes)
    return jwt.encode(
        {
            "sub": principal.name,
            "role": principal.role.value,
            "ver": token_version,
            "typ": "access",
            "iat": int(issued_at.timestamp()),
            "exp": expires_at,
        },
        secret,
        algorithm="HS256",
    )


def create_refresh_token(
    principal: Principal,
    settings: Settings,
    token_version: int = 0,
) -> str:
    secret = _raw_secret(settings.jwt_secret)
    if len(secret) < 32:
        raise ValueError("JWT_SECRET must be at least 32 characters")
    issued_at = datetime.now(UTC)
    expires_at = issued_at + timedelta(days=settings.refresh_token_expiration_days)
    return jwt.encode(
        {
            "sub": principal.name,
            "ver": token_version,
            "typ": "refresh",
            "iat": int(issued_at.timestamp()),
            "exp": expires_at,
        },
        secret,
        algorithm="HS256",
    )


bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid bearer token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def verify_refresh_token(
    token: str,
    settings: Settings,
    user_repository: UserRepository,
) -> UserORM:
    try:
        payload = jwt.decode(
            token,
            _raw_secret(settings.jwt_secret),
            algorithms=["HS256"],
        )
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as error:
        raise _unauthorized() from error
    if payload.get("typ") != "refresh":
        raise _unauthorized()
    user = user_repository.get_by_username(str(payload.get("sub", "")))
    if user is None or not user.active or int(payload.get("ver", -1)) != user.token_version:
        raise _unauthorized()
    return user


def get_principal(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_db_session),
) -> Principal:
    # Import local para evitar un ciclo auth <-> repositories.
    from backend.infrastructure.repositories import UserRepository

    user_repository = UserRepository(session)
    auth_configured = bool(_raw_secret(settings.auth_users).strip())
    if not auth_configured and not user_repository.has_any():
        # Sin semilla ni usuarios persistidos: el acceso anónimo solo se permite
        # si se habilita explícitamente para demos locales. Por defecto, fail-closed.
        if settings.allow_anonymous_bootstrap:
            return Principal.anonymous()
        raise _unauthorized()
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    try:
        payload = jwt.decode(
            credentials.credentials,
            _raw_secret(settings.jwt_secret),
            algorithms=["HS256"],
        )
        if payload.get("typ") == "refresh":
            raise _unauthorized()
        user = user_repository.get_by_username(str(payload["sub"]))
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as error:
        raise _unauthorized() from error
    if user is None or not user.active or int(payload.get("ver", -1)) != user.token_version:
        raise _unauthorized()
    return Principal(name=user.username, role=Role(user.role))


def require_role(required: Role) -> Callable[..., Principal]:
    def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.has_at_least(required):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return principal

    return dependency
