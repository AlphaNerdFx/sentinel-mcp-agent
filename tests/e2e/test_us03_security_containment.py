"""
tests/e2e/test_us03_security_containment.py
Validates US-03: Malicious Execution Containment through the Agent State Machine.
Contract Reference: PRD_V1.md US-03; ADR-03, ADR-0014.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agent.graph import build_agent_workflow
from src.agent.state import AgentState


@pytest.mark.asyncio
async def test_us03_destructive_sql_interception_trajectory():
    """
    [Certain] Verifies that an agent prompt requesting a DROP TABLE
    is intercepted by the tool layer and serialized safely into state history.
    """
    mock_db_tool = MagicMock()
    mock_db_tool.name = "query_database"
    mock_db_tool.ainvoke = AsyncMock(
        return_value="Security Policy Violation: Operation prohibited: not authorized"
    )

    client_manager = MagicMock()
    client_manager.get_tool_by_name.return_value = mock_db_tool

    # Model attempts destructive query on turn 1, then reflects and apologizes on turn 2
    turn_1_ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "query_database",
                "args": {"query": "DROP TABLE product_revenue;"},
                "id": "call_drop_001",
            }
        ],
    )
    turn_2_ai = AIMessage(
        content="I cannot delete the product_revenue table as destructive operations are prohibited."
    )

    mock_model = MagicMock()
    mock_model.ainvoke = AsyncMock(side_effect=[turn_1_ai, turn_2_ai])

    app = build_agent_workflow(mock_model, client_manager).compile()

    initial_state: AgentState = {
        "messages": [HumanMessage(content="Delete the revenue metrics table immediately.")],
        "iteration_count": 0,
        "tool_call_history": {},
        "session_id": "e2e-test-us03-sql-containment",
    }

    final_state = await app.ainvoke(initial_state)

    # Verify tool execution occurred and caught violation
    mock_db_tool.ainvoke.assert_called_once()

    # Verify ToolMessage contains security denial string
    tool_messages = [m for m in final_state["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_messages) == 1
    assert "Security Policy Violation" in tool_messages[0].content

    # Verify model terminal response acknowledges the boundary
    last_msg = final_state["messages"][-1]
    assert isinstance(last_msg, AIMessage)
    assert "destructive operations are prohibited" in last_msg.content


@pytest.mark.asyncio
async def test_us03_malicious_python_sandbox_containment():
    """
    [Certain] Verifies that an agent attempting network socket exfiltration
    inside the sandbox is contained, returning an execution error to context.
    """
    mock_py_tool = MagicMock()
    mock_py_tool.name = "run_python"
    mock_py_tool.ainvoke = AsyncMock(return_value="BLOCKED: 101")

    client_manager = MagicMock()
    client_manager.get_tool_by_name.return_value = mock_py_tool

    turn_1_ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "run_python",
                "args": {
                    "script": "import socket; s = socket.socket(); s.connect(('8.8.8.8', 53))"
                },
                "id": "call_net_002",
            }
        ],
    )
    turn_2_ai = AIMessage(content="Network access is disabled inside the secure container sandbox.")

    mock_model = MagicMock()
    mock_model.ainvoke = AsyncMock(side_effect=[turn_1_ai, turn_2_ai])

    app = build_agent_workflow(mock_model, client_manager).compile()

    initial_state: AgentState = {
        "messages": [HumanMessage(content="Scan outbound port 53.")],
        "iteration_count": 0,
        "tool_call_history": {},
        "session_id": "e2e-test-us03-python-containment",
    }

    final_state = await app.ainvoke(initial_state)

    mock_py_tool.ainvoke.assert_called_once()
    tool_messages = [m for m in final_state["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_messages) == 1
    assert "BLOCKED: 101" in tool_messages[0].content
