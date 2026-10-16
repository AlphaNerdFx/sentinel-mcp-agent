"""
src/agent/state.py
Production AgentState Schema & Commutative Domain-Aware AST Loop Sentinel.
Contract Reference: SPEC_V1.md COMP-01, COMP-03; PRD_V1.md ADR-0016.
"""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any, Dict, Sequence, TypedDict, cast

import sqlglot
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from sqlglot import exp


class AgentState(TypedDict):
    """
    [Certain] Immutable state container passed across all LangGraph nodes.
    Enforces add_messages append-only reducer and tracks SHA-256 loop counts.
    """

    messages: Annotated[Sequence[BaseMessage], add_messages]
    iteration_count: int
    tool_call_history: dict[str, int]
    session_id: str


def _canonicalize_ast(expression: Any) -> exp.Expression:
    """
    [Certain] Canonicalizes SQL AST via sqlglot.transform visitor pattern.
    Eliminates in-place pointer corruption by generating clean node replacements.
    Handles:
    1. Commutative binary equality (id = 1 vs 1 = id)
    2. Relational operator inversion (1000 < revenue vs revenue > 1000)
    3. Commutative logical junctions (A AND B vs B AND A; A OR B vs B OR A)
    """

    def _transform(node: exp.Expression) -> exp.Expression:
        # 1. Commutative Equality & Inequality
        if isinstance(node, (exp.EQ, exp.NEQ)):
            left = node.this
            right = node.expression
            if left is not None and right is not None:
                left_sql = left.sql(dialect="sqlite")
                right_sql = right.sql(dialect="sqlite")
                if left_sql > right_sql:
                    # Return new instance to prevent pointer collisions
                    return type(node)(this=right, expression=left)

        # 2. Relational Operator Inversion
        elif isinstance(node, (exp.GT, exp.LT, exp.GTE, exp.LTE)):
            left = node.this
            right = node.expression
            if left is not None and right is not None:
                left_sql = left.sql(dialect="sqlite")
                right_sql = right.sql(dialect="sqlite")
                if left_sql > right_sql:
                    inversion_map = {
                        exp.GT: exp.LT,
                        exp.LT: exp.GT,
                        exp.GTE: exp.LTE,
                        exp.LTE: exp.GTE,
                    }
                    target_cls = inversion_map[type(node)]
                    return cast(exp.Expression, target_cls(this=right, expression=left))

        # 3. Commutative Logical Operators (AND / OR)
        elif isinstance(node, (exp.And, exp.Or)):
            target_cls = type(node)
            operands: list[exp.Expression] = []

            def collect_operands(n: exp.Expression) -> None:
                if isinstance(n, target_cls):
                    if n.this is not None:
                        collect_operands(n.this)
                    if n.expression is not None:
                        collect_operands(n.expression)
                else:
                    operands.append(n)

            collect_operands(node)
            # Lexicographical sort by canonical SQLite serialization
            sorted_ops = sorted(operands, key=lambda x: x.sql(dialect="sqlite"))

            reconstructed = sorted_ops[0]
            for op in sorted_ops[1:]:
                reconstructed = target_cls(this=reconstructed, expression=op)
            return reconstructed

        return node

    return cast(exp.Expression, expression.transform(_transform))


def canonical_fingerprint(tool_name: str, tool_args: Dict[str, Any]) -> str:
    """
    [Certain] Computes collision-resistant semantic SHA-256 fingerprint.
    Normalizes SQL queries via sqlglot AST and sorts general JSON parameters.
    """
    payload: Dict[str, Any] = tool_args
    if tool_name == "query_database" and "query" in tool_args:
        try:
            parsed = sqlglot.parse_one(tool_args["query"], read="sqlite")
            if parsed is not None:
                canonical_ast = _canonicalize_ast(parsed)
                normalized_query = canonical_ast.sql(dialect="sqlite", normalize=True)
                payload = {"query": normalized_query}
            else:
                payload = tool_args
        except Exception:
            payload = tool_args

    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest_input = f"{tool_name}:{serialized}".encode("utf-8")
    return hashlib.sha256(digest_input).hexdigest()
