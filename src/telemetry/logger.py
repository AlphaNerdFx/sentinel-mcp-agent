import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, Field

class TelemetryMetrics(BaseModel):
    latency_ms: float
    input_tokens: int
    output_tokens: int
    tokens_per_second: float = 0.0
    shadow_cost_usd: float = 0.0

class TelemetryEvent(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    session_id: str
    event_type: Literal["llm_completion", "tool_executed", "circuit_break", "force_end", "security_violation"]
    node: str
    metrics: TelemetryMetrics
    payload: Dict[str, Any]

class StructuredLogger:
    """Emits un-nested, machine-readable JSON telemetry lines strictly to sys.stderr."""

    def __init__(self, stream: Any = None) -> None:
        # ADR-0013: Reserve sys.stdout for MCP JSON-RPC communication; write logs to stderr
        self.stream = stream or sys.stderr

    def log_event(
        self,
        event_type: str,
        node: str,
        metrics: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emits a structured JSON log line matching PRD Section 4.3 schema."""
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "node": node,
            "metrics": metrics or {},
            "payload": payload or {},
        }
        json_line = json.dumps(record, separators=(",", ":"))
        self.stream.write(json_line + "\n")
        self.stream.flush()

    # Backwards-compatibility aliases for legacy Phase 1 callers
    def log(self, *args: Any, **kwargs: Any) -> None:
        if "event_type" in kwargs:
            self.log_event(**kwargs)
        elif len(args) >= 2:
            self.log_event(event_type=args[0], node=args[1])
        else:
            self.log_event(event_type="generic_log", node="system", payload={"data": str(args)})

    def emit(self, *args: Any, **kwargs: Any) -> None:
        self.log(*args, **kwargs)