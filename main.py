"""
Sentinel MCP Agent - CLI Application Entrypoint (COMP-09)
Standard: Forward Deployed Engineering (FDE) Production Grade
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from typing import Any, Optional

import aiosqlite
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from src.agent.graph import build_agent_workflow
from src.agent.mcp_client import MCPClientManager
from src.agent.model_adapter import get_model
from src.telemetry.logger import StructuredLogger


def parse_arguments() -> argparse.Namespace:
    """Parses command-line arguments enforcing COMP-09 interface contracts."""
    parser = argparse.ArgumentParser(
        description="Sentinel MCP Agent - Enterprise Tool Calling Runtime",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        default=None,
        help="One-shot prompt to process. If omitted, requires --interactive.",
    )
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Run as an interactive asynchronous REPL session.",
    )
    parser.add_argument(
        "-s",
        "--session-id",
        type=str,
        default=None,
        help="UUID to resume an existing checkpointed session from .agent_state.db.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable human-readable trace logging on sys.stderr.",
    )
    return parser.parse_args()


async def execute_turn(
    app: Any,
    prompt: str,
    session_id: str,
    logger: StructuredLogger,
) -> tuple[int, Optional[str]]:
    """
    Executes a single conversational graph turn.
    Returns: (exit_code, response_text)
    POSIX Status Codes:
      0: Success
      1: Runtime Fault
      3: Circuit Breaker Interception / Iteration Ceiling
    """
    config = {"configurable": {"thread_id": session_id}}
    initial_state = {
        "messages": [HumanMessage(content=prompt)],
        "iteration_count": 0,
        "tool_call_history": {},
        "session_id": session_id,
    }

    try:
        final_state = await app.ainvoke(initial_state, config=config)

        # Check for iteration ceiling abort (force_end_node activation)
        if final_state.get("iteration_count", 0) >= 10:
            logger.log_event(
                event_type="iteration_ceiling_hit",
                node="force_end_node",
                payload={"session_id": session_id, "iterations": final_state["iteration_count"]},
            )
            return 3, "Execution halted: Iteration cap exceeded."

        messages = final_state.get("messages", [])
        last_message = messages[-1] if messages else None

        if isinstance(last_message, AIMessage):
            return 0, str(last_message.content)
        return 0, str(last_message) if last_message else "No response generated."

    except Exception as exc:
        logger.log_event(
            event_type="runtime_fault",
            node="orchestrator",
            payload={"error": str(exc), "session_id": session_id},
        )
        sys.stderr.write(f"\n[FATAL ERROR] {exc}\n")
        return 1, None


async def main() -> int:
    """CLI orchestrator entrypoint returning deterministic POSIX exit codes."""
    args = parse_arguments()

    if not args.prompt and not args.interactive:
        sys.stderr.write(
            "Error: Must provide either a prompt positional argument or --interactive flag.\n"
        )
        return 1

    session_id = args.session_id or str(uuid.uuid4())
    logger = StructuredLogger(session_id=session_id, stream=sys.stderr, verbose=args.verbose)

    # Initialize FastMCP Native Client Manager (ADR-0019)
    client_manager = MCPClientManager(server_script="src/server.py")
    try:
        tools = await client_manager.initialize()
        model = get_model(tools=tools)

        # ADR-0017 / SPEC COMP-01: Persistent WAL State Machine Checkpointer
        async with aiosqlite.connect(".agent_state.db") as conn:
            await conn.execute("PRAGMA journal_mode=WAL;")
            await conn.execute("PRAGMA busy_timeout = 5000;")
            checkpointer = AsyncSqliteSaver(conn)

            # Compile graph WITH persistent checkpointer
            app = build_agent_workflow(model, client_manager).compile(checkpointer=checkpointer)

            if args.interactive:
                sys.stderr.write(f"=== Sentinel MCP Agent Interactive Session [{session_id}] ===\n")
                sys.stderr.write("Type ':q', 'quit', or 'exit' to end the session.\n\n")

                while True:
                    try:
                        sys.stderr.write("sentinel> ")
                        sys.stderr.flush()
                        user_input = await asyncio.get_event_loop().run_in_executor(
                            None, sys.stdin.readline
                        )
                        if not user_input:
                            break

                        cleaned_input = user_input.strip()
                        if cleaned_input in (":q", "quit", "exit"):
                            break
                        if not cleaned_input:
                            continue

                        exit_code, response = await execute_turn(
                            app,
                            cleaned_input,
                            session_id,
                            logger
                        )
                        if response:
                            sys.stdout.write(f"{response}\n")
                            sys.stdout.flush()

                    except (KeyboardInterrupt, asyncio.CancelledError):
                        sys.stderr.write("\nSession terminated by user.\n")
                        break

            else:
                exit_code, response = await execute_turn(app, args.prompt, session_id, logger)
                if response:
                    sys.stdout.write(f"{response}\n")
                    sys.stdout.flush()
                return exit_code

    finally:
        await client_manager.close()


if __name__ == "__main__":
    exit_status = asyncio.run(main())
    sys.exit(exit_status)
