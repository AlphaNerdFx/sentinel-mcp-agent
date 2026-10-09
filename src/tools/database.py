import sqlite3
import os
from typing import List, Dict, Any

class SecurityViolationError(Exception):
    """Raised when query execution triggers security policy barriers."""
    pass

class DatabaseEngine:
    def __init__(self, db_path: str = "company_metrics.db") -> None:
        self.db_path = db_path
        self._init_db_file()

    def _init_db_file(self) -> None:
        """Seeds demo data if database does not exist."""
        if not os.path.exists(self.db_path):
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE product_revenue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_name TEXT NOT NULL,
                    quarter TEXT NOT NULL,
                    revenue REAL NOT NULL
                );
            """)
            cursor.executemany("""
                INSERT INTO product_revenue (product_name, quarter, revenue)
                VALUES (?, ?, ?)
            """, [
                ("CloudEngine", "Q1-2026", 1250000.00),
                ("CloudEngine", "Q2-2026", 1450000.00),
                ("DataShield", "Q1-2026", 800000.00),
                ("DataShield", "Q2-2026", 950000.00),
            ])
            conn.commit()
            conn.close()

    @staticmethod
    def _authorizer_guard(action_code: int, param1: Any, param2: Any, db_name: Any, trigger_name: Any) -> int:
        """
        C-level interceptor. Only read operations are permitted.
        Rejects all write, update, delete, schema alteration, or pragma calls.
        """
        SAFE_ACTIONS = {
            sqlite3.SQLITE_SELECT,
            sqlite3.SQLITE_READ,
            sqlite3.SQLITE_FUNCTION
        }
        if action_code in SAFE_ACTIONS:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    def execute_query(self, sql_query: str) -> List[Dict[str, Any]]:
        """Executes a read-only query using both URI flags and SQLite authorizer."""
        # Normalize and run a preliminary check for denial-of-service attempts
        normalized = sql_query.strip().lower()
        if "recursive" in normalized:
            raise SecurityViolationError("Recursive queries are prohibited to prevent denial-of-service.")

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
        except sqlite3.DatabaseError as e:
            if "not authorized" in str(e).lower():
                raise SecurityViolationError(f"Security Policy Violation: Operation prohibited: {e}")
            raise RuntimeError(f"Database Execution Fault: {e}")

    def get_schema(self) -> str:
        """Exposes schema for MCP Resource binding."""
        uri_path = f"file:{os.path.abspath(self.db_path)}?mode=ro"
        conn = sqlite3.connect(uri_path, uri=True)
        cursor = conn.cursor()
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='product_revenue';")
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else ""