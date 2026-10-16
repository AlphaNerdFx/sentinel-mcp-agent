"""
tests/e2e/test_us01_multistep_query.py
Validates US-01: Multi-Step Analytical Query Resolution (SQL -> Python -> Synthesis).
Contract Reference: PRD_V1.md US-01; SPEC_V1.md COMP-01.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.agent.graph import build_agent_workflow
from src.agent.state import AgentState


@pytest.mark.asyncio
async def test_us01_multistep_sql_to_python_pipeline():
    """
    [Certain] Verifies that an analytical query executes query_database,
    processes results via run_python, and returns a verified answer in <= 4 steps.
    """
    # 1. Setup Mock FastMCP Tools
    mock_db_tool = MagicMock()
    mock_db_tool.name = "query_database"
    mock_db_tool.ainvoke = AsyncMock(
        return_value='[{"product_name": "CloudEngine", "quarter": "Q1", "revenue": 100000.0}]'
    )

    mock_python_tool = MagicMock()
    mock_python_tool.name = "run_python"
    mock_python_tool.ainvoke = AsyncMock(return_value="115000.0\n")

    client_manager = MagicMock()

    def get_tool(name: str):
        if name == "query_database":
            return mock_db_tool
        if name == "run_python":
            return mock_python_tool
        raise ValueError(f"Unknown tool: {name}")

    client_manager.get_tool_by_name.side_effect = get_tool

    # 2. Program deterministic multi-step LLM trajectory (3 turns <= 4 iterations)
    turn_1_ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "query_database",
                "args": {
                    "query": "SELECT revenue FROM product_revenue WHERE product_name = 'CloudEngine';"
                },
                "id": "call_sql_001",
            }
        ],
    )
    turn_2_ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "run_python",
                "args": {"script": "print(100000.0 * 1.15)"},
                "id": "call_py_002",
            }
        ],
    )
    turn_3_ai = AIMessage(
        content="The total CloudEngine revenue is projected to increase by 15% to $115,000.00."
    )

    mock_model = MagicMock()
    mock_model.ainvoke = AsyncMock(side_effect=[turn_1_ai, turn_2_ai, turn_3_ai])

    # 3. Compile Graph Workflow
    app = build_agent_workflow(mock_model, client_manager).compile()

    initial_state: AgentState = {
        "messages": [
            HumanMessage(content="Calculate total CloudEngine revenue and project a 15% increase.")
        ],
        "iteration_count": 0,
        "tool_call_history": {},
        "session_id": "e2e-test-us01-trajectory",
    }

    # 4. Execute LangGraph FSM
    final_state = await app.ainvoke(initial_state)

    # 5. Invariant Assertions
    # Invariant: Iteration count must not exceed 4 steps (PRD US-01 Acceptance Criteria)
    assert final_state["iteration_count"] <= 4

    # Assert both tools were executed in sequence
    mock_db_tool.ainvoke.assert_called_once()
    mock_python_tool.ainvoke.assert_called_once()

    # Assert terminal message is final synthesis
    last_msg = final_state["messages"][-1]
    assert isinstance(last_msg, AIMessage)
    assert "115,000.00" in last_msg.content
