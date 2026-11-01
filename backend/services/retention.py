from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json

from backend.auth import Principal, Role
from backend.infrastructure.config import get_settings, validate_runtime_settings
from backend.infrastructure.database import SessionLocal, create_tables, engine
from backend.infrastructure.repositories import AuditRepository, RetentionRepository
from backend.schemas import RetentionRunResponse


class RetentionService:
    def __init__(
        self,
        retention_repository: RetentionRepository,
        audit_repository: AuditRepository,
        incidents_days: int,
        audit_days: int,
    ) -> None:
        self._retention_repository = retention_repository
        self._audit_repository = audit_repository
        self._incidents_days = incidents_days
        self._audit_days = audit_days

    def run(
        self,
        *,
        actor: Principal,
        dry_run: bool = True,
        incidents_days: int | None = None,
        audit_days: int | None = None,
    ) -> RetentionRunResponse:
        effective_incidents_days = (
            incidents_days if incidents_days is not None else self._incidents_days
        )
        effective_audit_days = (
            audit_days if audit_days is not None else self._audit_days
        )
        if effective_incidents_days <= 0:
            raise ValueError("incidents_days must be greater than zero")
        if effective_audit_days <= 0:
            raise ValueError("audit_days must be greater than zero")

        now = datetime.now(timezone.utc)
        incident_cutoff = now - timedelta(days=effective_incidents_days)
        audit_cutoff = now - timedelta(days=effective_audit_days)

        if dry_run:
            incident_counts = self._retention_repository.preview_incidents(
                incident_cutoff,
            )
            audit_logs = self._retention_repository.preview_audit_logs(audit_cutoff)
        else:
            incident_counts = self._retention_repository.delete_incidents(
                incident_cutoff,
            )
            audit_logs = self._retention_repository.delete_audit_logs(audit_cutoff)

        result = RetentionRunResponse(
            dry_run=dry_run,
            incident_cutoff=incident_cutoff,
            audit_cutoff=audit_cutoff,
            incidents_matched=incident_counts.incidents,
            triage_results_matched=incident_counts.triage_results,
            triage_reviews_matched=incident_counts.triage_reviews,
            audit_logs_matched=audit_logs,
        )

        self._audit_repository.record(
            actor=actor,
            action="retention.run",
            resource_type="retention",
            details={
                "dry_run": dry_run,
                "incident_cutoff": incident_cutoff.isoformat(),
                "audit_cutoff": audit_cutoff.isoformat(),
                "incidents_matched": result.incidents_matched,
                "triage_results_matched": result.triage_results_matched,
                "triage_reviews_matched": result.triage_reviews_matched,
                "audit_logs_matched": result.audit_logs_matched,
            },
        )
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Purga incidencias y auditoría antiguas de forma controlada.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Ejecuta la purga; sin esta opción solo se calcula el dry-run.",
    )
    parser.add_argument(
        "--incidents-days",
        type=int,
        default=None,
        help="Antigüedad mínima de incidencias en días (default: RETENTION_DAYS).",
    )
    parser.add_argument(
        "--audit-days",
        type=int,
        default=None,
        help="Antigüedad mínima de auditoría en días (default: AUDIT_RETENTION_DAYS).",
    )
    parser.add_argument(
        "--actor",
        default="retention-cli",
        help="Nombre del actor que se registrará en auditoría.",
    )
    args = parser.parse_args(argv)

    if args.incidents_days is not None and args.incidents_days <= 0:
        parser.error("--incidents-days must be greater than zero")
    if args.audit_days is not None and args.audit_days <= 0:
        parser.error("--audit-days must be greater than zero")
    if not args.actor.strip():
        parser.error("--actor must not be empty")
    if len(args.actor) > 100:
        parser.error("--actor must be 100 characters or fewer")

    settings = get_settings()
    validate_runtime_settings(settings)
    create_tables(engine)

    with SessionLocal() as session:
        service = RetentionService(
            RetentionRepository(session),
            AuditRepository(session),
            settings.retention_days,
            settings.audit_retention_days,
        )
        result = service.run(
            actor=Principal(
                name=args.actor,
                role=Role.ADMIN,
                authenticated=False,
            ),
            dry_run=not args.apply,
            incidents_days=args.incidents_days,
            audit_days=args.audit_days,
        )

    print(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
