import asyncio
import json
import logging

import backend.main as main_module
from backend.logging_config import JsonFormatter


def test_json_formatter_emits_only_operational_fields() -> None:
    record = logging.LogRecord(
        name="backend.services.incident",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="incident_analysis_completed",
        args=(),
        exc_info=None,
    )
    record.incident_id = "incident-id"
    record.status = "analyzed"
    record.duration_ms = 12.5
    record.users_created = 2

    payload = json.loads(JsonFormatter().format(record))

    assert payload["event"] == "incident_analysis_completed"
    assert payload["incident_id"] == "incident-id"
    assert payload["status"] == "analyzed"
    assert payload["duration_ms"] == 12.5
    assert payload["users_created"] == 2
    assert "description" not in payload
    assert "prompt" not in payload
    assert "secret" not in payload


def test_lifespan_bootstrap_log_uses_a_non_reserved_field(monkeypatch, caplog) -> None:
    caplog.set_level(logging.INFO, logger="backend.main")
    monkeypatch.setattr(main_module, "configure_logging", lambda: None)
    monkeypatch.setattr(main_module, "validate_runtime_settings", lambda _: None)
    monkeypatch.setattr(main_module, "create_tables", lambda _: None)
    monkeypatch.setattr(main_module, "bootstrap_users", lambda: 1)

    async def run_lifespan() -> None:
        async with main_module.lifespan(main_module.app):
            pass

    asyncio.run(run_lifespan())

    records = [
        record
        for record in caplog.records
        if record.name == "backend.main" and record.getMessage() == "auth_users_bootstrapped"
    ]
    assert len(records) == 1
    assert records[0].users_created == 1
