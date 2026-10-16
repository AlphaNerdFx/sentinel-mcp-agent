"""
Tool-Call Loop Detector & Circuit Breaker (COMP-03)
Enforces SHA-256 argument fingerprinting with semantic AST normalization
to intercept repetitive or cycling tool-calling patterns.
"""

import hashlib
import json
import sys
from typing import Any, Dict, List, Tuple

import sqlglot


class ToolCallCircuitBreaker:
    @classmethod
    def normalize_arguments(cls, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalizes arguments into a canonical format prior to hashing.
        Translates SQL queries into normalized AST representations to prevent syntax drift.
        """
        cleaned_args = dict(args)

        if tool_name == "query_database" and "sql_query" in cleaned_args:
            raw_sql = str(cleaned_args["sql_query"])
            try:
                # Parse SQL into an Abstract Syntax Tree and transpile to canonical SQLite dialect
                expression = sqlglot.parse_one(raw_sql, read="sqlite")
                # Normalize: uppercase keywords, eliminate extraneous whitespace and padding
                canonical_sql = expression.sql(dialect="sqlite", pretty=False)
                cleaned_args["sql_query"] = canonical_sql
            except Exception as parse_error:
                # If AST parsing fails (e.g., malformed syntax), fallback to basic whitespace normalization
                sys.stderr.write(f"[DEBUG] SQL AST normalization bypassed: {parse_error}\n")
                sys.stderr.flush()
                cleaned_args["sql_query"] = " ".join(raw_sql.strip().split()).lower()

        return cleaned_args

    @classmethod
    def compute_fingerprint(cls, tool_name: str, args: Dict[str, Any]) -> str:
        """
        Computes a deterministic SHA-256 fingerprint:
        SHA256( tool_name + ":" + canonical_json(normalized_args) )
        """
        normalized = cls.normalize_arguments(tool_name, args)
        try:
            canonical_payload = json.dumps(
                normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True
            )
        except (TypeError, ValueError):
            # Fallback representation for non-serializable types
            canonical_payload = repr(sorted(normalized.items()))

        raw_signature = f"{tool_name}:{canonical_payload}"
        return hashlib.sha256(raw_signature.encode("utf-8")).hexdigest()

    @classmethod
    def inspect_call(
        cls, fingerprint: str, history: List[str], strike_threshold: int = 3
    ) -> Tuple[bool, int]:
        """
        Evaluates current fingerprint occurrences against execution history.
        Returns: (is_tripped: bool, current_strike_count: int)
        """
        # Count prior occurrences of identical signature in session history
        prior_occurrences = history.count(fingerprint)
        current_strike = prior_occurrences + 1

        is_tripped = current_strike >= strike_threshold
        return is_tripped, current_strike
