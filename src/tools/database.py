"""
src/tools/database.py
Relational Database Access Engine with C-Authorizer and Read-Only Connection Enforcement.
Contract Reference: SPEC_V1.md COMP-06; PRD_V1.md ADR-0014, US-03.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any, Dict, List, Optional


class SecurityViolationError(Exception):
    """Raised when SQLite query violates the read-only security authorizer."""

    pass


class DatabaseEngine:
    """
    [Certain] Low-level SQLite database access engine enforcing C-level security.
    """

    def __init__(self, db_path: str = "company_metrics.db") -> None:
        self.db_path = db_path

    def _authorizer_guard(
        self,
        action_code: int,
        param1: Optional[str],
        param2: Optional[str],
        db_name: Optional[str],
        trigger_name: Optional[str],
    ) -> int:
        """
        [Certain] C-level authorizer callback (ADR-0014).
        Permits only SELECT, READ, and basic scalar functions.
        """
        safe_actions = {
            sqlite3.SQLITE_SELECT,
            sqlite3.SQLITE_READ,
            sqlite3.SQLITE_FUNCTION,
        }
        if action_code in safe_actions:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    def execute_query(self, sql_query: str) -> List[Dict[str, Any]]:
        """
        [Certain] Executes read-only query using URI ro mode and C-authorizer.
        Raises SecurityViolationError on unauthorized actions.
        """
        normalized = sql_query.strip().lower()
        if "recursive" in normalized:
            raise SecurityViolationError(
                "Recursive queries are prohibited to prevent denial-of-service."
            )

        uri_path = f"file:{os.path.abspath(self.db_path)}?mode=ro"
        try:
            conn = sqlite3.connect(uri_path, uri=True, timeout=2.0)
            conn.set_authorizer(self._authorizer_guard)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql_query)
            rows = cursor.fetchall()
            results = [dict(row) for row in rows]
            conn.close()
            return results
        except sqlite3.DatabaseError as err:
            if "not authorized" in str(err).lower():
                raise SecurityViolationError(
                    f"Security Policy Violation: Operation prohibited: {err}"
                ) from err
            raise RuntimeError(f"Database Execution Fault: {err}") from err

    def get_schema(self) -> str:
        """[Certain] Returns schema of product_revenue table."""
        uri_path = f"file:{os.path.abspath(self.db_path)}?mode=ro"
        conn = sqlite3.connect(uri_path, uri=True, timeout=2.0)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='product_revenue';"
        )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else ""


_default_engine: Optional[DatabaseEngine] = None


def query_database(query: str) -> List[Dict[str, Any]] | str:
    """
    [Certain] Public FastMCP tool wrapper.
    Catches SecurityViolationError and serializes it to an agent-safe string.
    """
    global _default_engine
    if _default_engine is None:
        _default_engine = DatabaseEngine()
    try:
        return _default_engine.execute_query(query)
    except SecurityViolationError as sec_err:
        return str(sec_err)
    except Exception as exc:
        return f"Database Query Error: {exc}"
