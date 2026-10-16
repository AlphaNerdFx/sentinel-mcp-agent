# tests/e2e/test_us02_loop_interception.py
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agent.nodes import tool_node
from src.agent.state import AgentState


@pytest.mark.asyncio
async def test_circuit_breaker_intercepts_strike_three():
    """[Certain] Verifies repetitive tool invocations halt at strike 3 with synthetic ToolMessage."""
    # Setup mock MCP client manager
    client_manager = MagicMock()
    tool_mock = MagicMock()
    tool_mock.ainvoke = AsyncMock(return_value="Success execution result")
    client_manager.get_tool_by_name.return_value = tool_mock

    # Initial state with 2 identical invocations already registered
    tool_name = "query_database"
    tool_args = {"query": "SELECT * FROM product_revenue WHERE 1 = id;"}

    # Calculate target fingerprint
    from src.agent.state import canonical_fingerprint

    fp = canonical_fingerprint(tool_name, tool_args)

    state: AgentState = {
        "messages": [
            HumanMessage(content="Calculate quarterly revenue"),
            AIMessage(
                content="",
                tool_calls=[{"name": tool_name, "args": tool_args, "id": "call_loop_strike_3"}],
            ),
        ],
        "iteration_count": 2,
        "tool_call_history": {fp: 2},  # Strike count = 2
        "session_id": "test-session-circuit-breaker",
    }

    # Execute tool node
    result = await tool_node(state, client_manager)

    # 1. Assert physical MCP execution was NOT called (Intercepted)
    tool_mock.ainvoke.assert_not_called()

    # 2. Assert synthetic message was returned with wire compliance
    messages = result["messages"]
    assert len(messages) == 1
    assert isinstance(messages[0], ToolMessage)
    assert messages[0].tool_call_id == "call_loop_strike_3"
    assert "CIRCUIT BREAKER" in messages[0].content.upper()

    # 3. Assert strike count incremented to 3
    assert result["tool_call_history"][fp] == 3
