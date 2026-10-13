"""src/agent/state.py
Deterministic State Schema & Domain-Aware Canonical Hashing Engine.
"""
from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any, Sequence, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
import sqlglot
from sqlglot import exp


def _canonicalize_ast(node: exp.Expression) -> exp.Expression:
    """Recursively commutes binary equality operators so that operand order is deterministic."""
    if isinstance(node, (exp.EQ, exp.NEQ)):
        left_sql = node.this.sql(dialect="sqlite")
        right_sql = node.expression.sql(dialect="sqlite")
        # Ensure left operand is always lexicographically less than or equal to right operand
        if left_sql > right_sql:
            node.set("this", sqlglot.parse_one(right_sql, read="sqlite"))
            node.set("expression", sqlglot.parse_one(left_sql, read="sqlite"))
    return node


def canonical_fingerprint(tool_name: str, tool_args: dict[str, Any]) -> str:
    """Computes a collision-resistant SHA-256 fingerprint.
    
    Normalizes SQL queries by parsing to AST, sorting commutative equality operands,
    and transpiling to standard SQLite syntax.
    """
    normalized_payload: dict[str, Any] = {}

    for key, value in sorted(tool_args.items()):
        if tool_name == "query_database" and key == "query" and isinstance(value, str):
            try:
                # 1. Parse into AST
                parsed = sqlglot.parse_one(value, read="sqlite")
                # 2. Transform commutative binary operators
                transformed = parsed.transform(_canonicalize_ast)
                # 3. Transpile back to canonical normalized SQL
                normalized_payload[key] = transformed.sql(dialect="sqlite", normalize=True)
            except Exception:
                normalized_payload[key] = value.strip()
        else:
            normalized_payload[key] = value

    canonical_repr = (
        f"{tool_name}:"
        + json.dumps(normalized_payload, sort_keys=True, separators=(",", ":"))
    )
    return hashlib.sha256(canonical_repr.encode("utf-8")).hexdigest()


class AgentState(TypedDict):
    """Hermetic LangGraph Agent State."""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    iteration_count: int
    tool_call_history: dict[str, int]
    session_id: str