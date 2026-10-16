"""src/agent/nodes.py
State Machine Execution Nodes with Atomic Wire-Protocol Enforcement.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, ToolMessage

from src.agent.mcp_client import MCPClientManager
from src.agent.state import AgentState, canonical_fingerprint
from src.telemetry.cost import CostEngine
from src.telemetry.logger import StructuredLogger

logger = StructuredLogger()
cost_engine = CostEngine()


async def agent_node(state: AgentState, model: Any) -> Dict[str, Any]:
    """Invokes LLM, records token metrics, and emits structured telemetry."""
    start_time = time.perf_counter()
    response = await model.ainvoke(state["messages"])
    latency_ms = (time.perf_counter() - start_time) * 1000.0

    prompt_tokens = 0
    completion_tokens = 0
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        prompt_tokens = response.usage_metadata.get("input_tokens", 0)
        completion_tokens = response.usage_metadata.get("output_tokens", 0)
    elif "token_usage" in response.response_metadata:
        usage = response.response_metadata["token_usage"]
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

    cost_usd = cost_engine.calculate_cost(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        model_name=getattr(model, "model_name", "qwen2.5:7b-instruct-q4_K_M"),
    )

    logger.log_event(
        event_type="llm_completion",
        node="agent_node",
        metrics={
            "latency_ms": latency_ms,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": cost_usd,
        },
        payload={"session_id": state["session_id"], "iteration": state["iteration_count"]},
    )

    return {
        "messages": [response],
        "iteration_count": state["iteration_count"] + 1,
    }


async def tool_node(state: AgentState, client_manager: MCPClientManager) -> Dict[str, Any]:
    """Atomic Partition & Dispatch Node.
    Partitions tool calls into safe vs tripped. Safely executes non-tripped calls
    while injecting synthetic ToolMessages for tripped calls. Fulfills 100% of tool_call_ids.
    """
    last_message = state["messages"][-1]
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return {}

    history = dict(state.get("tool_call_history", {}))
    outgoing_messages: List[ToolMessage] = []

    for tool_call in last_message.tool_calls:
        name = tool_call["name"]
        args = tool_call["args"]
        call_id = tool_call["id"]

        fingerprint = canonical_fingerprint(name, args)
        count = history.get(fingerprint, 0) + 1
        history[fingerprint] = count

        if count >= 3:
            # Tripped: Bypass execution and emit synthetic ToolMessage
            logger.log_event(
                event_type="circuit_breaker_tripped",
                node="tool_node",
                metrics={"strike_count": count},
                payload={
                    "tool_name": name,
                    "tool_call_id": call_id,
                    "session_id": state["session_id"],
                },
            )
            outgoing_messages.append(
                ToolMessage(
                    tool_call_id=call_id,
                    content=(
                        f"CIRCUIT BREAKER TRIGGERED: Tool '{name}' has been called with "
                        f"identical arguments {count} times. Further execution is blocked. "
                        "Re-evaluate your strategy or synthesize your final response."
                    ),
                    name=name,
                )
            )
        else:
            # Safe: Dispatch to MCP client
            start_time = time.perf_counter()
            try:
                tool_instance = client_manager.get_tool_by_name(name)
                raw_output = await tool_instance.ainvoke(args)
                content = str(raw_output)
                is_error = False
            except Exception as exc:
                content = f"Error executing tool '{name}': {str(exc)}"
                is_error = True

            latency_ms = (time.perf_counter() - start_time) * 1000.0
            logger.log_event(
                event_type="tool_execution",
                node="tool_node",
                metrics={"latency_ms": latency_ms, "is_error": is_error},
                payload={
                    "tool_name": name,
                    "tool_call_id": call_id,
                    "session_id": state["session_id"],
                },
            )
            outgoing_messages.append(ToolMessage(tool_call_id=call_id, content=content, name=name))

    return {
        "messages": outgoing_messages,
        "tool_call_history": history,
    }


async def force_end_node(state: AgentState) -> Dict[str, Any]:
    """Reconciles dangling tool calls and terminates the graph cleanly."""
    last_message = state["messages"][-1]
    synthetic_messages: List[Any] = []

    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        for tool_call in last_message.tool_calls:
            synthetic_messages.append(
                ToolMessage(
                    tool_call_id=tool_call["id"],
                    content="SYSTEM: Iteration ceiling reached (10 cycles). Tool execution canceled.",
                    name=tool_call["name"],
                )
            )

    synthetic_messages.append(
        AIMessage(
            content="Maximum iteration limit reached (10). Operation halted by runtime policy."
        )
    )
    return {"messages": synthetic_messages}
