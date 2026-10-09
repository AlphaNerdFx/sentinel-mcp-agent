import sys
from datetime import datetime, timezone
from typing import Any, Dict, Literal
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
    @staticmethod
    def emit(event: TelemetryEvent) -> None:
        """
        Emits single-line JSON strictly to sys.stderr to avoid
        corrupting JSON-RPC streams running on sys.stdout.
        """
        try:
            line = event.model_dump_json()
        except Exception:
            # Fallback serialization to guarantee observability never crashes the host
            sanitized_payload = {k: str(v) for k, v in event.payload.items()}
            event.payload = sanitized_payload
            line = event.model_dump_json()
        
        sys.stderr.write(line + "\n")
        sys.stderr.flush()