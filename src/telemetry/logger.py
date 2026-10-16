"""
src/telemetry/logger.py
RFC 3339-Compliant Structured Telemetry Logger with Stream Segregation.
Contract Reference: SPEC_V1.md COMP-08; PRD_V1.md ADR-0013, Section 4.3.
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, TextIO


class StructuredLogger:
    """
    [Certain] Emits flat, un-nested JSON lines strictly to sys.stderr (ADR-0013).
    Guarantees session_id context propagation across all emitted records.
    """

    def __init__(self, session_id: Optional[str] = None, stream: Optional[TextIO] = None) -> None:
        self.session_id: str = session_id if session_id is not None else str(uuid.uuid4())
        self.stream: TextIO = stream if stream is not None else sys.stderr

    def log_event(
        self,
        event_type: str,
        node: str,
        metrics: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> None:
        """
        [Certain] Formats and writes a single JSON line terminated by \\n.
        Guarantees presence of timestamp, session_id, event_type, and node.
        """
        record: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id or self.session_id,
            "event_type": event_type,
            "node": node,
            "metrics": metrics or {},
            "payload": payload or {},
        }

        json_line = json.dumps(record, separators=(",", ":")) + "\n"
        self.stream.write(json_line)
        self.stream.flush()
