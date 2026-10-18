"""
Structured Telemetry & Cost Accounting Engine (COMP-08)
Standard: RFC 3339 Single-Line JSON to sys.stderr (ADR-0013)
"""

from __future__ import annotations

import json
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Optional, TextIO

current_session_id: ContextVar[Optional[str]] = ContextVar("current_session_id", default=None)


class StructuredLogger:
    """Emits structured RFC 3339 JSON telemetry records strictly to stderr."""

    def __init__(
        self,
        session_id: Optional[str] = None,
        stream: Optional[TextIO] = None,
        verbose: bool = False,
    ) -> None:
        self.session_id: str = session_id or str(uuid.uuid4())
        self.stream: TextIO = stream or sys.stderr
        self.verbose: bool = verbose

    def log_event(
        self,
        event_type: str,
        node: str,
        metrics: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> None:
        """Emits a single-line un-nested JSON record or formatted trace to sys.stderr."""
        ambient_id = current_session_id.get()
        active_session_id = session_id or ambient_id or self.session_id

        # Also extract session_id if legacy code passed it inside payload
        if payload and "session_id" in payload:
            active_session_id = payload.pop("session_id")

        timestamp = datetime.now(timezone.utc).isoformat()

        record: Dict[str, Any] = {
            "timestamp": timestamp,
            "session_id": active_session_id,
            "event_type": event_type,
            "node": node,
            "metrics": metrics or {},
            "payload": payload or {},
        }

        if self.verbose:
            # Human-readable ANSI colorized trace for CLI operators
            node_color = "\033[35m" if node == "agent_node" else "\033[33m"
            reset = "\033[0m"
            latency = (
                f" | Latency: {metrics.get('latency_ms', 0):.1f}ms"
                if metrics and "latency_ms" in metrics
                else ""
            )
            self.stream.write(f"{node_color}[{node.upper()}]{reset} {event_type}{latency}\n")
            self.stream.flush()
        else:
            # ADR-0013 / PRD Section 4.3 Machine-Readable Single-Line JSON
            self.stream.write(json.dumps(record, separators=(",", ":")) + "\n")
            self.stream.flush()
