"""
tests/unit/tools/test_sql_guardrails.py
Unit Test Suite for Relational Database Security Guardrails (C-Authorizer & URI ro).
Contract Reference: SPEC_V1.md COMP-06; PRD_V1.md ADR-0014, US-03.
"""

import os
import sqlite3

import pytest

from src.tools.database import DatabaseEngine, SecurityViolationError

TEST_DB_PATH = "test_guardrails_metrics.db"


@pytest.fixture(scope="module")
def setup_test_db():
    """[Certain] Seeds an isolated SQLite database file and tears it down."""
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)

    conn = sqlite3.connect(TEST_DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE product_revenue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            quarter TEXT NOT NULL,
            revenue REAL NOT NULL
        );
    """)
    cursor.executemany(
        """
        INSERT INTO product_revenue (product_name, quarter, revenue)
        VALUES (?, ?, ?);
    """,
        [
            ("CloudEngine", "Q1", 100000.0),
            ("CloudEngine", "Q2", 125000.0),
            ("DataPipeline", "Q1", 45000.0),
        ],
    )
    conn.commit()
    conn.close()

    yield TEST_DB_PATH

    for ext in ["", "-wal", "-shm"]:
        target = f"{TEST_DB_PATH}{ext}"
        if os.path.exists(target):
            try:
                os.remove(target)
            except OSError:
                pass


@pytest.fixture
def db_engine(setup_test_db):
    """[Certain] Returns an instance of DatabaseEngine bound to test DB."""
    return DatabaseEngine(db_path=setup_test_db)


def _get_row_count(db_path: str) -> int:
    """[Certain] Raw helper to get row count directly."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    count = conn.execute("SELECT COUNT(*) FROM product_revenue;").fetchone()[0]
    conn.close()
    return count


class TestSQLGuardrails:
    def test_legitimate_select_queries_succeed(self, db_engine):
        """[Certain] Verifies standard analytical SELECT operations are permitted."""
        query = (
            "SELECT product_name, SUM(revenue) as total FROM product_revenue GROUP BY product_name;"
        )
        results = db_engine.execute_query(query)
        assert len(results) == 2
        assert any(r["product_name"] == "CloudEngine" for r in results)

    @pytest.mark.parametrize(
        "malicious_query",
        [
            "DROP TABLE product_revenue;",
            "DROP TABLE IF EXISTS product_revenue;",
            "CREATE TABLE attacker_table (id INT);",
            "ALTER TABLE product_revenue ADD COLUMN leaked TEXT;",
        ],
    )
    def test_ddl_modifications_blocked(self, db_engine, malicious_query, setup_test_db):
        """
        [Certain] Verifies DDL statements raise SecurityViolationError at the engine layer
        without modifying physical database contents.
        """
        initial_count = _get_row_count(setup_test_db)

        with pytest.raises(SecurityViolationError) as exc_info:
            db_engine.execute_query(malicious_query)

        assert "Operation prohibited" in str(exc_info.value)
        assert _get_row_count(setup_test_db) == initial_count

    @pytest.mark.parametrize(
        "destructive_query",
        [
            "DELETE FROM product_revenue WHERE id = 1;",
            "DELETE/**/FROM product_revenue;",
            "UPDATE product_revenue SET revenue = 0.0;",
            "INSERT INTO product_revenue (product_name, quarter, revenue) VALUES ('Malware', 'Q1', 0.0);",
        ],
    )
    def test_dml_mutations_blocked(self, db_engine, destructive_query, setup_test_db):
        """
        [Certain] Verifies DML mutations raise SecurityViolationError at the engine layer
        even when obfuscated with inline comments.
        """
        initial_count = _get_row_count(setup_test_db)

        with pytest.raises(SecurityViolationError) as exc_info:
            db_engine.execute_query(destructive_query)

        assert "Operation prohibited" in str(exc_info.value)
        assert _get_row_count(setup_test_db) == initial_count

    def test_attach_database_smuggling_denied(self, db_engine, setup_test_db):
        """[Certain] Verifies ATTACH DATABASE is blocked by C-authorizer (ADR-0014)."""
        attack_query = "ATTACH DATABASE ':memory:' AS shadow_db;"
        with pytest.raises(SecurityViolationError):
            db_engine.execute_query(attack_query)

    def test_system_pragma_tampering_denied(self, db_engine):
        """[Certain] Verifies system-altering PRAGMAs raise SecurityViolationError."""
        attack_query = "PRAGMA writable_schema = 1;"
        with pytest.raises(SecurityViolationError):
            db_engine.execute_query(attack_query)

    def test_query_database_tool_wrapper_catches_exception_for_wire(
        self, setup_test_db, monkeypatch
    ):
        """
        [Certain] Verifies that the public MCP tool adapter catches SecurityViolationError
        and converts it to a safe string for LLM consumption without raising.
        """
        from src.tools import database

        test_engine = DatabaseEngine(db_path=setup_test_db)
        monkeypatch.setattr(database, "_default_engine", test_engine)

        result = database.query_database("DROP TABLE product_revenue;")
        assert isinstance(result, str)
        assert "Security Policy Violation" in result or "prohibited" in result

    def test_readonly_connection_mode_failsafe(self, setup_test_db):
        """[Certain] Defense-in-depth: URI mode=ro blocks writes at the VFS layer."""
        conn = sqlite3.connect(f"file:{setup_test_db}?mode=ro", uri=True)
        with pytest.raises(sqlite3.OperationalError) as exc_info:
            conn.execute("UPDATE product_revenue SET revenue = 999.0 WHERE id = 1;")

        assert "attempt to write a readonly database" in str(exc_info.value).lower()
        conn.close()
