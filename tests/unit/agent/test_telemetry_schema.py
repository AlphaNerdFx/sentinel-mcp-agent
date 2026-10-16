"""
tests/unit/agent/test_telemetry_schema.py
Validates stream demultiplexing strictly to sys.stderr, JSON Lines schema conformity,
and dual-accounting cost metrics.
Contract Reference: SPEC_V1.md COMP-08; PRD_V1.md Section 4.3, ADR-0013, ADR-09.
"""

import io
import json
import sys
from datetime import datetime

import pytest

from src.telemetry.cost import CostEngine
from src.telemetry.logger import StructuredLogger


class TestCostEngine:
    def test_shadow_cost_calculation(self):
        """
        [Certain] Verifies calculation against PRD baseline pricing:
        $0.15 / 1M prompt tokens, $0.60 / 1M completion tokens.
        """
        cost_engine = CostEngine()
        # 1,000,000 prompt tokens = $0.15; 1,000,000 completion tokens = $0.60
        cost = cost_engine.calculate_cost(prompt_tokens=1_000_000, completion_tokens=1_000_000)
        assert pytest.approx(cost, 1e-6) == 0.75

        # Typical invocation: 450 prompt, 82 completion
        single_turn_cost = cost_engine.calculate_cost(prompt_tokens=450, completion_tokens=82)
        expected = (450 * 0.15 / 1e6) + (82 * 0.60 / 1e6)
        assert pytest.approx(single_turn_cost, 1e-7) == expected

    def test_token_throughput_calculation(self):
        """[Certain] Verifies tokens-per-second calculation."""
        cost_engine = CostEngine()
        # 100 tokens generated in 2,000 ms = 50 tokens/sec
        tps = cost_engine.calculate_tokens_per_second(completion_tokens=100, latency_ms=2000.0)
        assert tps == 50.0

        # Zero latency division guard
        zero_latency_tps = cost_engine.calculate_tokens_per_second(
            completion_tokens=100, latency_ms=0.0
        )
        assert zero_latency_tps == 0.0


class TestStructuredLogger:
    def test_stream_segregation_enforcement(self, capsys):
        """
        [Certain] ADR-0013: Verifies logging writes strictly to sys.stderr
        leaving sys.stdout untouched for FastMCP transport frames.
        """
        logger = StructuredLogger(stream=sys.stderr)
        logger.log_event(
            event_type="tool_execution",
            node="tool_node",
            metrics={"latency_ms": 150.0},
            payload={"tool_name": "query_database"},
        )

        captured = capsys.readouterr()
        # stdout must be completely empty
        assert captured.out == ""
        # stderr must contain the JSON event
        assert captured.err != ""
        assert "tool_execution" in captured.err

    def test_json_lines_schema_conformance(self):
        """
        [Certain] Verifies that output strictly adheres to PRD Section 4.3 JSON schema:
        un-nested top-level keys, RFC 3339 timestamp, and valid JSON types.
        """
        buffer = io.StringIO()
        logger = StructuredLogger(stream=buffer)

        logger.log_event(
            event_type="llm_completion",
            node="agent_node",
            metrics={
                "latency_ms": 1240.50,
                "prompt_tokens": 450,
                "completion_tokens": 82,
                "cost_usd": 0.0001167,
            },
            payload={"iteration": 1},
        )

        output = buffer.getvalue()
        # Must be terminated with a single newline (JSON Line)
        assert output.endswith("\n")
        lines = output.strip().split("\n")
        assert len(lines) == 1

        record = json.loads(lines[0])

        # Validate mandatory top-level schema keys
        assert "timestamp" in record
        assert "session_id" in record
        assert record["event_type"] == "llm_completion"
        assert record["node"] == "agent_node"
        assert isinstance(record["metrics"], dict)
        assert isinstance(record["payload"], dict)

        # Validate RFC 3339 ISO timestamp parsability
        parsed_dt = datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))
        assert parsed_dt.year >= 2026

        # Validate nested metrics values
        assert record["metrics"]["prompt_tokens"] == 450
        assert record["metrics"]["completion_tokens"] == 82
        assert record["metrics"]["cost_usd"] == 0.0001167
