from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from backend.api.schemas import UserCreate, UserResponse, UserUpdate
from backend.infrastructure.repositories import AuditRepository, UserRepository
from backend.security.auth import (
    BootstrapUser,
    Principal,
    Role,
    hash_password,
    verify_password,
)

logger = logging.getLogger(__name__)


class UserNotFoundError(Exception):
    pass


class UserConflictError(Exception):
    pass


@dataclass(frozen=True)
class LoginResult:
    principal: Principal
    user: UserResponse
    token_version: int


class UserService:
    def __init__(
        self,
        repository: UserRepository,
        audit_repository: AuditRepository | None = None,
    ) -> None:
        self._repository = repository
        self._audit_repository = audit_repository

    def bootstrap(self, seed: tuple[BootstrapUser, ...]) -> int:
        """Crea los usuarios iniciales que aún no existan en la base.

        No actualiza contraseñas ni roles existentes: a partir del primer
        arranque, la base de datos es la fuente de verdad.
        """
        created = []
        for item in seed:
            if self._repository.get_by_username(item.username) is not None:
                continue
            created.append(
                self._repository.create(
                    username=item.username,
                    password_hash=hash_password(item.password),
                    role=item.role,
                ),
            )
        if created:
            self._record_audit_safely(
                Principal.system(),
                "user.bootstrap",
                None,
                {
                    "created": len(created),
                    "roles": sorted({record.role for record in created}),
                },
            )
        return len(created)

    def login(self, username: str, password: str) -> LoginResult | None:
        record = self._repository.get_by_username(username)
        if record is None:
            # Mantiene un coste de verificación similar a un usuario real.
            verify_password(password, None)
            return None
        if not verify_password(password, record.password_hash):
            return None
        if not record.active:
            return None
        self._repository.mark_login(record)
        principal = Principal(name=record.username, role=Role(record.role))
        return LoginResult(
            principal=principal,
            user=self._repository.to_response(record),
            token_version=record.token_version,
        )

    def logout(self, principal: Principal) -> bool:
        """Revoca los tokens del usuario autenticado.

        Incrementa ``token_version``, de modo que cualquier JWT emitido antes
        del logout deja de ser válido en la siguiente petición. Devuelve
        ``False`` si el principal no corresponde a un usuario persistido.
        """
        record = self._repository.get_by_username(principal.name)
        if record is None:
            return False
        self._repository.revoke_tokens(record)
        self._record_audit_safely(
            principal,
            "user.logout",
            record.id,
            {"revoked": "all_sessions"},
        )
        return True

    def get(self, user_id: UUID) -> UserResponse:
        record = self._repository.get(user_id)
        if record is None:
            raise UserNotFoundError
        return self._repository.to_response(record)

    def list(self, *, limit: int, offset: int) -> tuple[list[UserResponse], int]:
        records, total = self._repository.list(limit=limit, offset=offset)
        return [self._repository.to_response(record) for record in records], total

    def create(self, data: UserCreate, actor: Principal) -> UserResponse:
        if self._repository.get_by_username(data.username) is not None:
            raise UserConflictError("Username already exists")
        record = self._repository.create(
            username=data.username,
            password_hash=hash_password(data.password),
            role=data.role,
        )
        self._record_audit_safely(
            actor,
            "user.create",
            record.id,
            {"role": record.role},
        )
        return self._repository.to_response(record)

    def update(
        self,
        user_id: UUID,
        data: UserUpdate,
        actor: Principal,
    ) -> UserResponse:
        record = self._repository.get(user_id)
        if record is None:
            raise UserNotFoundError

        target_role = Role(record.role)
        is_active_admin = record.active and target_role is Role.ADMIN
        if (
            is_active_admin
            and data.role is not None
            and data.role is not Role.ADMIN
            and self._repository.count_active_admins() <= 1
        ):
            raise UserConflictError("Cannot demote the last active admin")
        if is_active_admin and data.active is False and self._repository.count_active_admins() <= 1:
            raise UserConflictError("Cannot deactivate the last active admin")
        if data.active is False and record.username == actor.name:
            raise UserConflictError("Cannot deactivate your own user")

        changed_fields = sorted(
            key for key, value in data.model_dump(exclude_none=True).items() if value is not None
        )
        record = self._repository.update(
            record,
            password_hash=(hash_password(data.password) if data.password is not None else None),
            role=data.role,
            active=data.active,
        )
        details: dict = {"changed_fields": changed_fields}
        if data.role is not None:
            details["role"] = data.role.value
        if data.active is not None:
            details["active"] = data.active
        if data.password is not None:
            details["password_changed"] = True
        self._record_audit_safely(actor, "user.update", record.id, details)
        return self._repository.to_response(record)

    def deactivate(self, user_id: UUID, actor: Principal) -> UserResponse:
        return self.update(user_id, UserUpdate(active=False), actor)

    def _record_audit_safely(
        self,
        actor: Principal,
        action: str,
        user_id: str | None,
        details: dict,
    ) -> None:
        try:
            self._record_audit(actor, action, user_id, details)
        except Exception:
            logger.exception(
                "audit_write_failed",
                extra={"resource_type": "user", "resource_id": user_id},
            )

    def _record_audit(
        self,
        actor: Principal,
        action: str,
        user_id: str | None,
        details: dict,
    ) -> None:
        if self._audit_repository is None:
            return
        self._audit_repository.record(
            actor=actor,
            action=action,
            resource_type="user",
            resource_id=user_id,
            details=details,
        )
