# Technical Component Specifications (SPEC_V1.md)

**System Target:** Enterprise MCP Tool-Calling Agent with Observability
**Document Version:** 1.2.0 (Post-Phase 2 Architecture Ratification)
**Tracking PRD:** `PRD_V1.md` (v1.2.0)
**Standard:** Production-Grade Interface Contract

---

## Component Index

1. [COMP-01: Orchestration Engine & State Machine](#comp-01-orchestration-engine--state-machine)
2. [COMP-02: Model Provider Adapter](#comp-02-model-provider-adapter)
3. [COMP-03: Tool-Call Loop Detector & Circuit Breaker](#comp-03-tool-call-loop-detector--circuit-breaker)
4. [COMP-04: FastMCP Tool Server & Client Manager](#comp-04-fastmcp-tool-server--client-manager)
5. [COMP-05: Docker Container Sandbox Runner](#comp-05-docker-container-sandbox-runner)
6. [COMP-06: Relational Database Access Engine](#comp-06-relational-database-access-engine)
7. [COMP-07: Resilient Multi-Provider Search Engine](#comp-07-resilient-multi-provider-search-engine)
8. [COMP-08: Structured Telemetry & Cost Accounting Engine](#comp-08-structured-telemetry--cost-accounting-engine)
9. [COMP-09: CLI Application Entrypoint](#comp-09-cli-application-entrypoint)

---

### COMP-01: Orchestration Engine & State Machine

#### 1. Architectural Role & File Location
* **Target Files:** `src/agent/graph.py` & `src/agent/nodes.py`
* **Role:** [Certain] Implements a Deterministic Finite State Machine (FSM) via LangGraph coordinating reasoning, atomic tool execution, circuit breaking, and persistent SQLite WAL checkpointing.

#### 2. Public Interfaces & Typed Schemas

```python
from typing import Annotated, Any, Dict, Literal, Sequence, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from src.agent.mcp_client import MCPClientManager

class AgentState(TypedDict):
    """Immutable state container passed across all graph nodes."""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    iteration_count: int
    tool_call_history: dict[str, int]  # Maps SHA-256 fingerprints to strike counts
    session_id: str

async def agent_node(state: AgentState, model: Any) -> Dict[str, Any]:
    """Invokes LLM via non-streaming ainvoke, extracts token metrics, and emits telemetry."""
    ...

async def tool_node(state: AgentState, client_manager: MCPClientManager) -> Dict[str, Any]:
    """Atomic Partition & Dispatch Node: executes safe calls and injects synthetic ToolMessages for tripped calls."""
    ...

async def force_end_node(state: AgentState) -> Dict[str, Any]:
    """Reconciles dangling tool calls and generates terminal termination notice."""
    ...

def route_agent_output(state: AgentState) -> Literal["force_end", "tools", "end"]:
    """Conditional router determining transition out of agent_node."""
    ...

def build_agent_workflow(model: Any, client_manager: MCPClientManager) -> StateGraph:
    """Builds the 3-node ReAct StateGraph with pure asynchronous closures."""
    ...
```

#### 3. Invariants & Operational Rules
* Invariant 1 (Loop Cap): [Certain] If state["iteration_count"] >= 10, route_agent_output must return "force_end". Execution must never cycle back to agent_node.
* Invariant 2 (State Append-Only): Message history must use LangGraph's add_messages reducer to preserve chronological conversation traces.
* Invariant 3 (Async Closure Purity): Node wrappers in build_agent_workflow must be declared as explicit async def closures to preserve Python CO_COROUTINE flags.
* Invariant 4 (Persistent State): Production compilation must bind AsyncSqliteSaver targeting .agent_state.db with PRAGMA journal_mode=WAL; (ADR-0017).

### COMP-02: Model Provider Adapter
#### 1. Architectural Role & File Location
- Target File: src/agent/model_adapter.py
- Role: [Certain] Factory instantiating a tool-bound ChatOpenAI client, routing to local Ollama by default and falling back to cloud APIs in CI environments.

#### 2. Public Interfaces & Typed Schemas
```python
from typing import List, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool

def is_ollama_online(base_url: str = "http://localhost:11434") -> bool:
    """Probes the Ollama HTTP daemon version endpoint with a 2.0s deadline."""
    ...

def get_model(
    tools: Optional[List[BaseTool]] = None,
    temperature: float = 0.0,
    local_model: str = "qwen2.5:7b-instruct-q4_K_M",
    cloud_fallback_model: str = "gpt-4o-mini",
) -> BaseChatModel:
    """Returns a ChatOpenAI model instance with bound tool schemas and transport deadlines."""
    ...
```
#### 3. Invariants & Operational Rules
* Invariant 1 (Deterministic Sampling): [Certain] temperature must be hard-coded to 0.0 across all paths to enforce deterministic function calling.
* Invariant 2 (Transport Deadline): [Certain] HTTP socket timeout must resolve MODEL_TIMEOUT environment variable (default: 120.0s) to accommodate GBNF grammar compilation and WSL2 TTFT latency.
* Invariant 3 (Zero-Network CI Fallback): If Ollama is unreachable, fall back to cloud_fallback_model only if OPENAI_API_KEY is present and does not start with mock_.

### COMP-03: Tool-Call Loop Detector & Circuit Breaker
1. Architectural Role & File Location
- Target Files: src/agent/state.py & src/agent/nodes.py
- Role: [Certain] Computes collision-resistant semantic fingerprints and atomically intercepts repetitive failure loops.
2. Public Interfaces & Typed Schemas
```python
from typing import Any, Dict
import sqlglot
from sqlglot import exp

def _canonicalize_ast(node: exp.Expression) -> exp.Expression:
    """Recursively commutes binary equality operators so that operand order is deterministic."""
    ...

def canonical_fingerprint(tool_name: str, tool_args: Dict[str, Any]) -> str:
    """Computes SHA-256 digest of tool_name + commutative AST normalized arguments."""
    ...
```
3. Invariants & Operational Rules
- Invariant 1 (Commutative AST Invariance): [Certain] SQL queries passed to query_database must be parsed via sqlglot, transformed to commute binary equality expressions (1 = id → id = 1), and transpiled to canonical SQLite dialect before hashing (ADR-0016).
- Invariant 2 (Atomic Wire Compliance): If a fingerprint recurs ≥3 times, tool_node intercepts execution and injects a synthetic ToolMessage fulfilling the exact tool_call_id. Sibling non-tripped calls in the same turn execute normally (ADR-0018).

### COMP-04: FastMCP Tool Server & Client Manager
1. Architectural Role & File Location
- Target Files: src/server.py & src/agent/mcp_client.py
- Role: [Certain] Provides child server execution over stdio and manages native client communication without external adapter dependencies (ADR-0019).
2. Public Interfaces & Typed Schemas
```python
from typing import List
from fastmcp import FastMCP, Client
from fastmcp.client.transports import StdioTransport
from langchain_core.tools import StructuredTool

# Server Entrypoint (src/server.py)
mcp = FastMCP(name="Enterprise-Tool-Server")

# Client Lifecycle Manager (src/agent/mcp_client.py)
class MCPClientManager:
    def __init__(self, server_script: str = "src/server.py") -> None: ...
    async def initialize(self) -> List[StructuredTool]: ...
    def get_tool_by_name(self, name: str) -> StructuredTool: ...
    async def close(self) -> None: ...
```
3. Invariants & Operational Rules
- Invariant 1 (Stdio Stream Segregation): [Certain] sys.stdout is strictly reserved for JSON-RPC 2.0 communication frames. All diagnostic logging must route to sys.stderr (ADR-0013).
- Invariant 2 (Dynamic Schema Synthesis): MCPClientManager dynamically synthesizes Pydantic parameter schemas using pydantic.create_model() to guarantee runtime typing for LangChain StructuredTool instances.

### COMP-05: Docker Container Sandbox Runner
1. Architectural Role & File Location
- Target File: src/sandbox/docker_runner.py
- Role: [Certain] Executes untrusted Python code inside ephemeral, non-networked Linux containers via the Docker daemon socket.
2. Public Interfaces & Typed Schemas
```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ExecutionResult:
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: float
    timed_out: bool

class DockerPythonSandbox:
    def __init__(
        self,
        image: str = "python:3.11-slim",
        memory_limit: str = "256m",
        cpu_quota: float = 1.0,
        timeout_seconds: int = 5,
    ) -> None: ...
    def execute_code(self, script_contents: str) -> ExecutionResult: ...
```
3. Invariants & Operational Rules
- Invariant 1 (Network Elimination): Containers must run with network_mode="none".
- Invariant 2 (Ephemeral Destruction): In the finally block of execute_code, container.remove(force=True) must execute unconditionally.
- Invariant 3 (Filesystem Lockdown): The container root must be mounted with read_only=True and scratchpad restricted to tmpfs={"/tmp": "rw,size=16m"}.
- Invariant 4 (Hard Timeout): Wall-clock execution capped at 5.0 seconds.

### COMP-06: Relational Database Access Engine
1. Architectural Role & File Location
- Target File: src/tools/database.py
- Role: [Certain] Provides read-only access to SQLite, enforcing read-only constraints at the filesystem, connection, and C-engine parser layers.
2. Public Interfaces & Typed Schemas
```python
from typing import List, Dict, Any

class DatabaseEngine:
    def __init__(self, db_path: str = "company_metrics.db") -> None: ...
    def initialize_database(self) -> None: ...
    def get_schema(self) -> str: ...
    def execute_query(self, sql_query: str) -> List[Dict[str, Any]]: ...

def query_database(query: str) -> List[Dict[str, Any]] | str:
    """Module-level singleton convenience wrapper."""
    ...
```
3. Invariants & Operational Rules
- Invariant 1 (Read-Only Connection): SQLite connection strings must use URI mode: file:{db_path}?mode=ro.
- Invariant 2 (C-Level Authorizer): The connection must register sqlite3.Connection.set_authorizer denying all actions outside SQLITE_SELECT, SQLITE_READ, and SQLITE_FUNCTION (ADR-0014).

### COMP-07: Resilient Multi-Provider Search Engine
1. Architectural Role & File Location
- Target File: src/tools/search.py
- Role: [Certain] Implements Chain-of-Responsibility fallback search pipeline across DuckDuckGo, Tavily, and Brave Search.
2. Public Interfaces & Typed Schemas
```python
from typing import List, Literal, Optional
from pydantic import BaseModel

class SearchResultItem(BaseModel):
    title: str
    snippet: str
    source_url: str

class UnifiedSearchResponse(BaseModel):
    provider_used: Literal["DuckDuckGo", "Tavily", "BraveSearch", "Exhausted"]
    query: str
    results: List[SearchResultItem]
    def to_context_string(self) -> str: ...

class ResilientSearchEngine:
    def __init__(
        self,
        tavily_api_key: Optional[str] = None,
        brave_api_key: Optional[str] = None,
        timeout_seconds: float = 4.0,
    ) -> None: ...
    def search(self, query: str, max_results: int = 3) -> UnifiedSearchResponse: ...
```

3. Invariants & Operational Rules
- Invariant 1 (Strict Cascade): DuckDuckGo → Tavily → Brave Search.
- Invariant 2 (Total Exhaustion): If all fail, return UnifiedSearchResponse(provider_used="Exhausted", results=[]) without raising unhandled exceptions.

### COMP-08: Structured Telemetry & Cost Accounting Engine
1. Architectural Role & File Location
- Target Files: src/telemetry/logger.py & src/telemetry/cost.py
- Role: [Certain] Emits RFC 3339-compliant JSON lines to sys.stderr and tracks physical latency alongside shadow cloud API costs.
2. Public Interfaces & Typed Schemas
```python
from typing import Any, Dict, Optional

class CostEngine:
    DEFAULT_PRICING: Dict[str, Dict[str, float]]
    def calculate_cost(self, prompt_tokens: int, completion_tokens: int, model_name: str = ...) -> float: ...
    def calculate_tokens_per_second(self, completion_tokens: int, latency_ms: float) -> float: ...

class StructuredLogger:
    def __init__(self, stream: Any = None) -> None: ...
    def log_event(
        self,
        event_type: str,
        node: str,
        metrics: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None: ...
```

3. Invariants & Operational Rules
- Invariant 1 (Single-Line JSON to Stderr): [Certain] Every event must emit a single line of un-nested JSON to sys.stderr terminated with \n (ADR-0013).
- Invariant 2 (Dual Accounting): Every LLM step must calculate both latency metrics and shadow dollar spend ($0.15 / 1M prompt, $0.60 / 1M completion).

### COMP-09: CLI Application Entrypoint
1. Architectural Role & File Location
- Target File: main.py
- Role: [Certain] Primary executable interface supporting argument parsing, interactive REPL sessions, and POSIX exit codes.
2. Public Interfaces & Typed Schemas
```python
import argparse

def parse_arguments() -> argparse.Namespace: ...
async def main() -> int:
    """Returns POSIX status codes: 0 = success, 1 = error, 2 = security, 3 = circuit break."""
    ...
```
3. Invariants & Operational Rules
- Invariant 1 (POSIX Exit Codes): Explicit exit codes: 0 (Success), 1 (Error), 2 (Security Violation), 3 (Circuit Break / Iteration Ceiling).
- Invariant 2 (Session Resumption): Support --session-id <UUID> to resume persistent graph execution from .agent_state.db (ADR-0017).

## Verification Cross-Reference Matrix
|Component Identifier	| Primary Interface Contract|	Verification Target	|Target SLA / Limit|
| :------------------------ | :------------------------- | :---------------------------- | :---------------------------- |
|COMP-01 (Orchestration)	|AgentState FSM	|test_state_graph.py|	Max 10 turns|
|COMP-02 (Model Adapter)	|get_model() Factory|	test_model_adapter.py|	Temp = 0.0, 120s Timeout|
|COMP-03 (Circuit Breaker)	|canonical_fingerprint|	test_loop_detector.py|	Strike 3 Interception\
|COMP-04 (FastMCP Server)	|MCPClientManager Stdio|	test_mcp_server.py|	Zero raw prints on stdout\
|COMP-05 (Docker Sandbox)	|execute_code()|	test_sandbox_security.py|	5s Kill / 256MB Cap|
|COMP-06 (Database Engine)	|execute_query()| / C-Auth	test_sql_guardrails.py|	Read-only URI mode|
|COMP-07 (Search Engine)	|search() Cascade|	test_search_fallback.py|	3-Tier Fallback|
|COMP-08 (Telemetry)	|log_event() JSON Line|	test_telemetry_schema.py|	Emits to sys.stderr|
|COMP-09 (CLI Entrypoint)	|main() POSIX Exit|	test_cli_interface.py|	Deterministic Exit Codes|