"""Audit logging (plan §19).

Append-only JSONL, one file per run, plus a per-packet event stream. Every
event records the configuration that produced it so any artifact can later
be reconstructed.
"""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from cvreview.schemas.ingestion import AuditEvent
from cvreview.settings import VERSIONS

logger = structlog.get_logger()


class AuditLog:
    """Writes AuditEvent records as JSONL. Append-only by construction."""

    def __init__(self, path: Path, run_id: str) -> None:
        self.path = path
        self.run_id = run_id
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, stage: str, action: str, packet_id: str | None = None,
             **details: object) -> AuditEvent:
        event = AuditEvent(
            run_id=self.run_id,
            stage=stage,
            action=action,
            packet_id=packet_id,
            details={k: v for k, v in details.items() if v is not None},
            config=dict(VERSIONS),
        )
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n")
        logger.info(action, stage=stage, packet_id=packet_id,
                    **{k: v for k, v in details.items()
                       if isinstance(v, (str, int, float, bool))})
        return event
