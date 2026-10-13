"""scripts/verify_phase2_live.py
Live Physical Integration Test for Phase 2 State Machine & MCP Transport.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
import uuid

# Deterministic Root Anchoring: inject repository root into sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from src.agent.mcp_client import MCPClientManager
from src.agent.model_adapter import get_model
from src.agent.graph import build_agent_workflow


async def main() -> None:
    server_path = str(REPO_ROOT / "src" / "server.py")
    client_mgr = MCPClientManager(server_path)
    try:
        print("[1/5] Initializing FastMCP Client over Stdio...")
        tools = await client_mgr.initialize()
        print(f"      Discovered {len(tools)} tools: {[t.name for t in tools]}")

        print("[2/5] Initializing Local Model Factory...")
        model = get_model(tools=tools)

        print("[3/5] Building StateGraph Workflow...")
        workflow = build_agent_workflow(model, client_mgr)

        db_path = str(REPO_ROOT / ".test_phase2_state.db")
        print(f"[4/5] Establishing Async SQLite Checkpointer ({db_path})...")

        async with AsyncSqliteSaver.from_conn_string(db_path) as checkpointer:
            app = workflow.compile(checkpointer=checkpointer)

            session_id = str(uuid.uuid4())
            config = {"configurable": {"thread_id": session_id}}

            prompt = "What tables are available in the database? Query the metrics table for total product count."
            print(f"[5/5] Executing Live Trajectory for prompt: '{prompt}'...")

            initial_state = {
                "messages": [HumanMessage(content=prompt)],
                "iteration_count": 0,
                "tool_call_history": {},
                "session_id": session_id,
            }

            final_state = await app.ainvoke(initial_state, config=config)
            print("\n--- Final Agent Response ---")
            print(final_state["messages"][-1].content)
            print("\nPhase 2 Physical Verification: SUCCESSFUL")
    finally:
        await client_mgr.close()


if __name__ == "__main__":
    asyncio.run(main())