from __future__ import annotations

import secrets
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from hashlib import sha256

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from pydantic import SecretStr

from app.infrastructure.config import Settings, get_settings


MIN_API_KEY_LENGTH = 16


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
class _ApiKeyEntry:
    name: str
    role: Role
    digest: bytes


class ApiKeyStore:
    def __init__(self, entries: list[_ApiKeyEntry]) -> None:
        self._entries = tuple(entries)

    @property
    def enabled(self) -> bool:
        return bool(self._entries)

    def authenticate(self, provided_key: str | None) -> Principal | None:
        if not self.enabled:
            return Principal.anonymous()
        if not provided_key:
            return None

        provided_digest = sha256(provided_key.encode("utf-8")).digest()
        for entry in self._entries:
            if secrets.compare_digest(entry.digest, provided_digest):
                return Principal(name=entry.name, role=entry.role)
        return None


def _raw_api_keys(raw: str | SecretStr | None) -> str:
    if isinstance(raw, SecretStr):
        return raw.get_secret_value()
    return raw or ""


def parse_api_keys(raw: str | SecretStr | None) -> ApiKeyStore:
    """Parse API_KEYS using ``name:role:key,name:role:key``.

    The format is validated strictly and error messages never include the key.
    An empty value disables authentication.
    """

    raw_value = _raw_api_keys(raw)
    if not raw_value.strip():
        return ApiKeyStore([])

    entries: list[_ApiKeyEntry] = []
    names: set[str] = set()
    digests: set[bytes] = set()

    for index, raw_entry in enumerate(raw_value.split(","), start=1):
        entry = raw_entry.strip()
        if not entry:
            raise ValueError(f"API_KEYS entry {index} is empty")

        parts = entry.split(":", 2)
        if len(parts) != 3:
            raise ValueError("API_KEYS entries must use name:role:key format")

        name, raw_role, key = (part.strip() for part in parts)
        if not name:
            raise ValueError(f"API_KEYS entry {index} has an empty name")
        if len(name) > 100:
            raise ValueError(f"API_KEYS entry {index} name is too long")

        try:
            role = Role(raw_role.lower())
        except ValueError as error:
            raise ValueError(
                f"API_KEYS entry {index} has an invalid role",
            ) from error

        if len(key) < MIN_API_KEY_LENGTH:
            raise ValueError(
                f"API_KEYS entry {index} key must be at least "
                f"{MIN_API_KEY_LENGTH} characters",
            )

        if name in names:
            raise ValueError("API_KEYS contains a duplicate name")

        digest = sha256(key.encode("utf-8")).digest()
        if digest in digests:
            raise ValueError("API_KEYS contains duplicate keys")

        names.add(name)
        digests.add(digest)
        entries.append(_ApiKeyEntry(name=name, role=role, digest=digest))

    return ApiKeyStore(entries)


@lru_cache(maxsize=8)
def _build_api_key_store(raw: str) -> ApiKeyStore:
    return parse_api_keys(raw)


def get_api_key_store(raw: str | SecretStr | None) -> ApiKeyStore:
    return _build_api_key_store(_raw_api_keys(raw))


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_principal(
    api_key: str | None = Security(api_key_header),
    settings: Settings = Depends(get_settings),
) -> Principal:
    store = get_api_key_store(settings.api_keys)
    if not store.enabled:
        return Principal.anonymous()

    principal = store.authenticate(api_key)
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "X-API-Key"},
        )
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
