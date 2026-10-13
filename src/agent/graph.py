"""src/agent/graph.py
Deterministic State Machine Assembly with Pure Async Closures.
"""
from __future__ import annotations

from typing import Any, Dict, Literal
from langgraph.graph import StateGraph, END
from langchain_core.messages import AIMessage
from src.agent.state import AgentState
from src.agent.nodes import agent_node, tool_node, force_end_node
from src.agent.mcp_client import MCPClientManager


def route_agent_output(state: AgentState) -> Literal["force_end", "tools", "end"]:
    """Determines transition out of agent_node."""
    if state["iteration_count"] >= 10:
        return "force_end"

    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"

    return "end"


def build_agent_workflow(
    model: Any,
    client_manager: MCPClientManager,
) -> StateGraph:
    """Builds and wires the ReAct StateGraph with verified asynchronous closures."""
    workflow = StateGraph(AgentState)

    # Explicit async closures preserve the coroutine function signature
    async def run_agent(state: AgentState) -> Dict[str, Any]:
        return await agent_node(state, model)

    async def run_tools(state: AgentState) -> Dict[str, Any]:
        return await tool_node(state, client_manager)

    async def run_force_end(state: AgentState) -> Dict[str, Any]:
        return await force_end_node(state)

    workflow.add_node("agent", run_agent)
    workflow.add_node("tools", run_tools)
    workflow.add_node("force_end", run_force_end)

    workflow.set_entry_point("agent")

    workflow.add_conditional_edges(
        "agent",
        route_agent_output,
        {
            "force_end": "force_end",
            "tools": "tools",
            "end": END,
        },
    )

    workflow.add_edge("tools", "agent")
    workflow.add_edge("force_end", END)

    return workflow