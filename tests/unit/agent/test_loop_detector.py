"""
tests/unit/agent/test_loop_detector.py
Verifies commutative AST normalization, operator inversion, boolean permutations,
and general argument deduplication.
Contract Reference: SPEC_V1.md COMP-03; PRD_V1.md Section 4.2, ADR-0016.
"""

from src.agent.state import canonical_fingerprint


class TestLoopDetectorAST:
    def test_ast_commutative_equality_reordering(self):
        """[Certain] Verifies that binary equality operands commute identically."""
        q1 = "SELECT * FROM product_revenue WHERE id = 10;"
        q2 = "select * from product_revenue where 10 = id;"
        assert canonical_fingerprint("query_database", {"query": q1}) == canonical_fingerprint(
            "query_database", {"query": q2}
        )

    def test_ast_commutative_and_junctions(self):
        """[Certain] Verifies that AND boolean expressions sort canonically."""
        q1 = "SELECT * FROM product_revenue WHERE quarter = 'Q1' AND revenue > 5000.0;"
        q2 = "SELECT * FROM product_revenue WHERE revenue > 5000.0 AND quarter = 'Q1';"
        assert canonical_fingerprint("query_database", {"query": q1}) == canonical_fingerprint(
            "query_database", {"query": q2}
        )

    def test_ast_commutative_or_junctions(self):
        """[Certain] Verifies that OR boolean expressions sort canonically."""
        q1 = "SELECT * FROM product_revenue WHERE product_name = 'CloudEngine' OR quarter = 'Q4';"
        q2 = "SELECT * FROM product_revenue WHERE quarter = 'Q4' OR product_name = 'CloudEngine';"
        assert canonical_fingerprint("query_database", {"query": q1}) == canonical_fingerprint(
            "query_database", {"query": q2}
        )

    def test_ast_relational_operator_inversion(self):
        """
        [Certain] Verifies relational operator inversion:
        'revenue > 1000' and '1000 < revenue' represent the identical predicate.
        """
        q1 = "SELECT * FROM product_revenue WHERE revenue > 1000.0;"
        q2 = "SELECT * FROM product_revenue WHERE 1000.0 < revenue;"
        assert canonical_fingerprint("query_database", {"query": q1}) == canonical_fingerprint(
            "query_database", {"query": q2}
        )

    def test_ast_whitespace_and_casing_invariance(self):
        """[Certain] Verifies SQL keywords, spacing, and trailing semicolons normalize."""
        q1 = "SELECT id, product_name FROM product_revenue WHERE id = 1;"
        q2 = "select   id,   product_name   from   product_revenue   where   1 = id ;"
        assert canonical_fingerprint("query_database", {"query": q1}) == canonical_fingerprint(
            "query_database", {"query": q2}
        )

    def test_ast_subquery_canonicalization(self):
        """[Certain] Verifies nested subqueries undergo recursive AST canonicalization."""
        q1 = "SELECT * FROM (SELECT id, revenue FROM product_revenue WHERE 1 = id);"
        q2 = "select * from (select id, revenue from product_revenue where id = 1);"
        assert canonical_fingerprint("query_database", {"query": q1}) == canonical_fingerprint(
            "query_database", {"query": q2}
        )

    def test_ast_syntax_error_fallback(self):
        """
        [Certain] Verifies that malformed SQL does not raise unhandled exceptions,
        falling back gracefully to standard JSON serialization.
        """
        malformed_query = "SELECT FROM WHERE 1 = ;;"
        # Must execute without throwing sqlglot.errors.ParseError
        digest = canonical_fingerprint("query_database", {"query": malformed_query})
        assert isinstance(digest, str)
        assert len(digest) == 64  # Valid SHA-256 hex string

    def test_distinct_queries_produce_distinct_fingerprints(self):
        """[Certain] Collision avoidance: different predicates must produce distinct digests."""
        q1 = "SELECT * FROM product_revenue WHERE id = 1;"
        q2 = "SELECT * FROM product_revenue WHERE id = 2;"
        assert canonical_fingerprint("query_database", {"query": q1}) != canonical_fingerprint(
            "query_database", {"query": q2}
        )


class TestLoopDetectorGeneralTools:
    def test_json_general_tool_sorting(self):
        """[Certain] Verifies key ordering invariance in arbitrary JSON payloads."""
        p1 = {"script": "print('hello')", "timeout": 5}
        p2 = {"timeout": 5, "script": "print('hello')"}
        assert canonical_fingerprint("run_python", p1) == canonical_fingerprint("run_python", p2)

    def test_nested_json_payload_sorting(self):
        """[Certain] Verifies deeply nested JSON dictionaries sort deterministically."""
        p1 = {"meta": {"env": "prod", "retries": 3}, "query": "latency"}
        p2 = {"query": "latency", "meta": {"retries": 3, "env": "prod"}}
        assert canonical_fingerprint("web_search", p1) == canonical_fingerprint("web_search", p2)
