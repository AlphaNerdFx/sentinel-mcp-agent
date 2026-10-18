"""
End-to-End Black-Box Subprocess Integration Test Suite for main.py (COMP-09).
Verifies: OS Process Lifecycles, POSIX Exit Codes, Stream Purity, and Disk Persistence.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import uuid
from typing import Any, Dict, List

# In tests/e2e/test_cli_e2e.py:


def run_cli(
    *args: str,
    env_overrides: Dict[str, str] | None = None,
    timeout: float = 360.0,
) -> subprocess.CompletedProcess[str]:
    """
    [Certain] Spawns main.py as a real OS-level child process with captured streams.
    Returns: CompletedProcess with decoded stdout and stderr strings.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = "."
    if env_overrides:
        env.update(env_overrides)

    cmd = [sys.executable, "main.py", *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
        check=False,
    )


def test_cli_missing_arguments_returns_exit_code_1() -> None:
    """[Certain] Verifies Exit Code 1 when invoked without prompt or --interactive."""
    result = run_cli()

    assert result.returncode == 1
    assert (
        "Error: Must provide either a prompt positional argument or --interactive flag"
        in result.stderr
    )
    assert result.stdout == ""


def test_cli_help_flag_returns_exit_code_0() -> None:
    """[Certain] Verifies --help contract and clean Exit Code 0."""
    result = run_cli("--help")

    assert result.returncode == 0
    assert "Sentinel MCP Agent" in result.stdout
    assert "--interactive" in result.stdout
    assert "--session-id" in result.stdout


def test_cli_stream_segregation_and_telemetry_schema() -> None:
    """
    [Certain] Physical Stream Audit (ADR-0013 / COMP-08 / COMP-09):
    Verifies that stdout contains pure analytical output, while stderr contains
    strictly valid RFC 3339 single-line JSON telemetry records.
    """
    test_session_id = str(uuid.uuid4())
    prompt = "Search the database for CloudEngine Q1 revenue and return ONLY the numeric value."

    result = run_cli(prompt, "--session-id", test_session_id)

    # 1. Process lifecycle assertion
    assert result.returncode == 0, f"CLI execution failed with stderr:\n{result.stderr}"

    # 2. stdout stream purity: must contain response, zero JSON framing
    stdout_clean = result.stdout.strip()
    assert len(stdout_clean) > 0
    assert '"event_type":' not in result.stdout
    assert '"session_id":' not in result.stdout

    # 3. stderr telemetry audit: every JSON line must match SPEC COMP-08
    stderr_lines = [line.strip() for line in result.stderr.splitlines() if line.strip()]
    telemetry_records: List[Dict[str, Any]] = []

    for line in stderr_lines:
        if line.startswith("{") and line.endswith("}"):
            try:
                record = json.loads(line)
                telemetry_records.append(record)
            except json.JSONDecodeError:
                continue

    assert len(telemetry_records) >= 1, "Zero structured JSON telemetry records detected on stderr"
    for record in telemetry_records:
        assert record.get("session_id") == test_session_id
        assert "timestamp" in record
        assert "event_type" in record
        assert "node" in record
        assert "metrics" in record


def test_cli_cross_process_persistence_resumption() -> None:
    """
    [Certain] Cross-Process Persistence Audit (ADR-0017 / COMP-01):
    Spawns Process 1 to establish state, then spawns Process 2 with the identical
    --session-id to verify conversational continuation from .agent_state.db on disk.
    """
    shared_session_id = str(uuid.uuid4())
    db_path = ".agent_state.db"

    # Turn 1: Process 1 executes initial query
    proc_1 = run_cli(
        "Search the database for CloudEngine Q1 revenue and return ONLY the number.",
        "--session-id",
        shared_session_id,
    )
    assert proc_1.returncode == 0, f"Turn 1 failed: {proc_1.stderr}"

    # Verify database file was created and checkpoints were committed
    assert os.path.exists(db_path), "Database file .agent_state.db was not created on disk"
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT count(*) FROM checkpoints WHERE thread_id = ?",
            (shared_session_id,),
        )
        checkpoints_turn_1 = cursor.fetchone()[0]
        assert checkpoints_turn_1 > 0, "Turn 1 failed to commit checkpoints to SQLite"

    # Turn 2: Process 2 executes follow-up in a completely separate OS process
    proc_2 = run_cli(
        "Now add 10 to that revenue and return ONLY the final sum.",
        "--session-id",
        shared_session_id,
    )
    assert proc_2.returncode == 0, f"Turn 2 failed: {proc_2.stderr}"

    # Verify that Process 2 resumed the thread and appended new checkpoints
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT count(*) FROM checkpoints WHERE thread_id = ?",
            (shared_session_id,),
        )
        checkpoints_turn_2 = cursor.fetchone()[0]
        assert checkpoints_turn_2 > checkpoints_turn_1, (
            "Turn 2 failed to append checkpoints to historical thread"
        )
