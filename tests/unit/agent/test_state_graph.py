"""
tests/unit/agent/test_state_graph.py
Verifies LangGraph 3-node FSM topology, iteration routing, and iteration ceilings.
Contract Reference: SPEC_V1.md COMP-01; PRD_V1.md ADR-01, US-02.
"""

from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agent.graph import build_agent_workflow, route_agent_output
from src.agent.nodes import force_end_node
from src.agent.state import AgentState


class TestStateGraphFSM:
    def test_workflow_topology_contains_required_nodes(self):
        """[Certain] Verifies COMP-01 3-node topology: agent, tools, force_end."""
        mock_model = MagicMock()
        mock_client = MagicMock()
        workflow = build_agent_workflow(mock_model, mock_client)

        node_keys = workflow.nodes.keys()
        assert "agent" in node_keys
        assert "tools" in node_keys
        assert "force_end" in node_keys

    def test_router_routes_to_tools_on_tool_calls(self):
        """[Certain] Verifies route_agent_output routes to 'tools' when model emits calls."""
        state: AgentState = {
            "messages": [
                HumanMessage(content="Query"),
                AIMessage(
                    content="", tool_calls=[{"name": "query_database", "args": {}, "id": "1"}]
                ),
            ],
            "iteration_count": 1,
            "tool_call_history": {},
            "session_id": "test",
        }
        assert route_agent_output(state) == "tools"

    def test_router_routes_to_end_on_conversational_response(self):
        """[Certain] Verifies route_agent_output routes to 'end' when no tool calls exist."""
        state: AgentState = {
            "messages": [
                HumanMessage(content="Hello"),
                AIMessage(content="Hello! How can I assist you today?"),
            ],
            "iteration_count": 1,
            "tool_call_history": {},
            "session_id": "test",
        }
        assert route_agent_output(state) == "end"

    def test_router_enforces_iteration_ceiling_at_ten(self):
        """
        [Certain] Verifies Invariant 1: when iteration_count >= 10,
        route_agent_output MUST return 'force_end' regardless of tool calls.
        """
        state: AgentState = {
            "messages": [
                AIMessage(
                    content="", tool_calls=[{"name": "query_database", "args": {}, "id": "1"}]
                ),
            ],
            "iteration_count": 10,  # Hard ceiling reached
            "tool_call_history": {},
            "session_id": "test",
        }
        assert route_agent_output(state) == "force_end"

    @pytest.mark.asyncio
    async def test_force_end_node_reconciles_dangling_tool_calls(self):
        """
        [Certain] Verifies force_end_node synthesizes ToolMessages for unfulfilled
        calls to prevent wire protocol violations upon abort.
        """
        state: AgentState = {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[{"name": "query_database", "args": {}, "id": "dangling_call_1"}],
                ),
            ],
            "iteration_count": 10,
            "tool_call_history": {},
            "session_id": "test",
        }
        result = await force_end_node(state)
        messages = result["messages"]

        # Must synthesize ToolMessage fulfilling dangling_call_1 and terminal AIMessage
        assert any(
            isinstance(m, ToolMessage) and m.tool_call_id == "dangling_call_1" for m in messages
        )
        assert any(
            isinstance(m, AIMessage) and "Maximum iteration limit reached" in m.content
            for m in messages
        )
