"""
FastMCP Tool Server & Resource Registry (COMP-04)
Serves database, sandbox, and search primitives over stdio JSON-RPC 2.0.
Adheres strictly to ADR-0013 stream segregation: stdout is reserved for JSON-RPC;
all diagnostics and telemetry are routed to stderr.
"""

import json
import sys

from fastmcp import FastMCP

from src.sandbox.docker_runner import DockerPythonSandbox
from src.tools.database import DatabaseEngine, SecurityViolationError
from src.tools.search import ResilientSearchEngine

# Initialize FastMCP Server
mcp = FastMCP(
    name="Enterprise-Tool-Server",
)

# Instantiate tool backends
db_engine = DatabaseEngine()
search_engine = ResilientSearchEngine()
sandbox = DockerPythonSandbox()

# ============================================================================
# MCP RESOURCES
# ============================================================================


@mcp.resource("schema://main")
def get_db_schema() -> str:
    """
    Exposes the SQLite database schema as a read-only contextual MCP resource.
    Eliminates tool-call turn consumption for schema discovery.
    """
    try:
        schema = db_engine.get_schema()
        return schema if schema else "No schema found."
    except Exception as exc:
        sys.stderr.write(f"[ERROR] Failed to fetch schema resource: {exc}\n")
        sys.stderr.flush()
        return f"Error retrieving schema: {str(exc)}"


# ============================================================================
# MCP TOOLS
# ============================================================================


@mcp.tool()
def query_database(sql_query: str) -> str:
    """
    Executes a read-only SQL query against company_metrics.db.
    Guarded by C-level SQLite authorizer to prevent data mutation or deletion.
    """
    try:
        rows = db_engine.execute_query(sql_query)
        return json.dumps(rows, default=str)
    except SecurityViolationError as sec_err:
        sys.stderr.write(f"[SECURITY] Query rejected by policy: {sec_err}\n")
        sys.stderr.flush()
        return f"Security Violation: {str(sec_err)}"
    except Exception as err:
        sys.stderr.write(f"[ERROR] Database execution error: {err}\n")
        sys.stderr.flush()
        return f"Database Error: {str(err)}"


@mcp.tool()
def run_python(code: str) -> str:
    """
    Executes Python analytical code inside an isolated, non-networked Docker container.
    Imforces a 256MB RAM cap, 1.0 CPU limit, and 5-second hard execution timeout.
    """
    result = sandbox.execute_code(code)

    if result.timed_out:
        return "Execution Error: Script timed out after 5.0 seconds (SIGKILL issued)."

    if result.exit_code == 137:
        return "Execution Error: Memory limit exceeded (256MB cgroup ceiling)."

    if result.exit_code != 0:
        return f"Execution Fault (Exit Code {result.exit_code}):\n{result.stderr.strip()}"

    output = result.stdout.strip()
    return output if output else "Code executed successfully with zero stdout output."


@mcp.tool()
def web_search(query: str) -> str:
    """
    Executes resilient multi-provider web search using DuckDuckGo with fallback
    to Tavily and Brave Search. Returns structured summary text.
    """
    response = search_engine.search(query=query)
    return response.to_context_string()


# ============================================================================
# ENTRYPOINT
# ============================================================================

if __name__ == "__main__":
    # Invariant: Run strictly on stdio transport
    mcp.run(transport="stdio")
