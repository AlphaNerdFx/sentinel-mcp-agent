# Technical Component Specifications (SPEC_V1.md)

**System Target:** Sentinel MCP Agent (Enterprise Tool-Calling Agent with Observability)  
**Document Version:** 1.3.0 (Post-Phase 4 Architecture & CI/CD Ratification)  
**Tracking PRD:** `PRD_V1.md` (v1.3.0)  
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
from __future__ import annotations
from typing import Annotated, Any, Dict, Literal, Sequence, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from src.agent.mcp_client import MCPClientManager

class AgentState(TypedDict):
    """Immutable state container passed across all graph nodes."""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    iteration_count: int
    tool_call_history: dict[str, int]
    session_id: str

async def agent_node(state: AgentState, model: Any) -> Dict[str, Any]:
    """Invokes LLM via non-streaming ainvoke, records token metrics, and emits telemetry."""
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
* Invariant 2 (Append-Only Reducer): Conversation history must use LangGraph's add_messages reducer to preserve chronological conversation traces without state mutation.
* Invariant 3 (Async Closure Purity): Node wrappers in build_agent_workflow must be declared as explicit async def closures to preserve Python CO_COROUTINE flags.
* Invariant 4 (Persistent State): Production compilation must bind AsyncSqliteSaver targeting .agent_state.db with PRAGMA journal_mode=WAL; (ADR-0017).
### COMP-02: Model Provider Adapter
#### 1. Architectural Role & File Location
* Target File: src/agent/model_adapter.py
* Role: [Certain] Factory instantiating a tool-bound ChatOpenAI client, routing to local Ollama by default and falling back to cloud APIs in CI environments.
* 2. Public Interfaces & Typed Schemas
```python
from __future__ import annotations
from typing import Any, List, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool

def is_ollama_online(base_url: str = "http://localhost:11434") -> bool:
    """Probes the Ollama HTTP daemon version endpoint with a 2.0s deadline."""
    ...

def get_model(
    tools: Optional[List[BaseTool]] = None,
    temperature: float = 0.0,
    local_model: str = "qwen2.5:7b-instruct-q4_K_M",
    cloud_fallback_model: str = "gpt-4o-mini",
) -> BaseChatModel | Runnable[Any, Any]:
    """Returns a ChatOpenAI model instance with bound tool schemas and transport deadlines."""
    ...
```
#### 3. Invariants & Operational Rules
* Invariant 1 (Deterministic Sampling): [Certain] temperature must be hard-coded to 0.0 across all execution paths.
* Invariant 2 (Transport Deadline): [Certain] HTTP socket timeout must resolve MODEL_TIMEOUT environment variable (default: 120.0s) to accommodate local GPU KV-cache expansion.
* Invariant 3 (Secret Str Encapsulation): All API keys must be wrapped in pydantic.SecretStr to prevent leakages in stack traces.
### COMP-03: Tool-Call Loop Detector & Circuit Breaker
#### 1. Architectural Role & File Location
* Target Files: src/agent/state.py & src/agent/nodes.py
* Role: [Certain] Computes collision-resistant semantic fingerprints and atomically intercepts repetitive failure loops.
#### 2. Public Interfaces & Typed Schemas
```python
from __future__ import annotations
from typing import Any, Dict
import sqlglot
from sqlglot import exp

def _canonicalize_ast(expression: Any) -> exp.Expression:
    """Recursively canonicalizes SQL AST via sqlglot.transform visitor pattern."""
    ...

def canonical_fingerprint(tool_name: str, tool_args: Dict[str, Any]) -> str:
    """Computes SHA-256 digest of tool_name + commutative AST normalized arguments."""
    ...
```
#### 3. Invariants & Operational Rules
Invariant 1 (Commutative AST Invariance): [Certain] SQL queries passed to query_database must be parsed via sqlglot, transformed to commute binary equality, logical junctions, and relational inversions, and transpiled to SQLite dialect before hashing (ADR-0016).
Invariant 2 (Atomic Wire Compliance): If a fingerprint recurs 
≥3 times, tool_node intercepts execution and injects a synthetic ToolMessage fulfilling the exact tool_call_id. Sibling non-tripped calls execute normally (ADR-0018).
### COMP-04: FastMCP Tool Server & Client Manager
#### 1. Architectural Role & File Location
* Target Files: src/server.py & src/agent/mcp_client.py
* Role: [Certain] Provides child server execution over stdio and manages native client communication without external adapter dependencies (ADR-0019).
#### 2. Public Interfaces & Typed Schemas
```python
from __future__ import annotations
from typing import Any, List
from fastmcp import FastMCP
from langchain_core.tools import StructuredTool
from pydantic import BaseModel

mcp = FastMCP(name="Enterprise-Tool-Server")

class MCPClientManager:
    def __init__(self, server_script: str = "src/server.py") -> None: ...
    async def initialize(self) -> List[StructuredTool]: ...
    def _create_pydantic_schema(self, tool_name: str, schema_dict: dict[str, Any]) -> type[BaseModel]: ...
    def get_tool_by_name(self, name: str) -> StructuredTool: ...
    async def close(self) -> None: ...
```
#### 3. Invariants & Operational Rules
* Invariant 1 (Stdio Stream Segregation): [Certain] sys.stdout is strictly reserved for JSON-RPC 2.0 communication frames. All diagnostic logging must route to sys.stderr (ADR-0013).
* Invariant 2 (Immutable Dynamic Schemas): Type mapping in _create_pydantic_schema must use immutable dictionary lookup tables (dict[str, type[Any]]) to prevent variable type narrowing.
### COMP-05: Docker Container Sandbox Runner
#### 1. Architectural Role & File Location
* Target File: src/sandbox/docker_runner.py
* Role: [Certain] Executes untrusted Python code inside ephemeral, non-networked Linux containers via the Docker daemon socket.
#### 2. Public Interfaces & Typed Schemas
```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ExecutionResult:
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: float
    timed_out: bool

class DockerDaemonUnavailableError(Exception):
    pass

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
#### 3.  Invariants & Operational Rules
* Invariant 1 (Network Elimination): Containers must execute with network_mode="none".
* Invariant 2 (Ephemeral Destruction): In the finally block of execute_code, container.remove(force=True) must execute unconditionally.
* Invariant 3 (Root Immutability): Root filesystem mounted with read_only=True and scratchpad restricted to tmpfs={"/tmp": "rw,size=16m"}.
* Invariant 4 (Exception Chaining): Daemon connection errors must be chained with raise ... from exc (Ruff B904).
COMP-06: Relational Database Access Engine
#### 1. Architectural Role & File Location
* Target File: src/tools/database.py
* Role: [Certain] Provides read-only access to SQLite, enforcing read-only constraints at the filesystem, connection, and C-engine parser layers.
#### 2. Public Interfaces & Typed Schemas
```python
from typing import Any, Dict, List

class SecurityViolationError(Exception):
    pass

class DatabaseEngine:
    def __init__(self, db_path: str = "company_metrics.db") -> None: ...
    def initialize_database(self) -> None: ...
    def get_schema(self) -> str: ...
    def execute_query(self, sql_query: str) -> List[Dict[str, Any]]: ...

def query_database(query: str) -> List[Dict[str, Any]] | str:
    """Public MCP Tool Facade."""
    ...
```
#### 3. Invariants & Operational Rules
* Invariant 1 (Read-Only Connection): SQLite URI connection strings must use file:{db_path}?mode=ro.
* Invariant 2 (C-Level Authorizer): The connection must register sqlite3.Connection.set_authorizer denying all actions outside SQLITE_SELECT, SQLITE_READ, and SQLITE_FUNCTION (ADR-0014).
* Invariant 3 (Self-Seeding Fresh Clones): If os.path.exists(self.db_path) is False, initialize_database() must seed schema and records automatically before mode=ro connections are attempted.
### COMP-07: Resilient Multi-Provider Search Engine
#### 1. Architectural Role & File Location
* Target File: src/tools/search.py
* Role: [Certain] Implements Chain-of-Responsibility fallback search pipeline across DuckDuckGo, Tavily, and Brave Search.
#### 2. Public Interfaces & Typed Schemas
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
    def _duckduckgo_search(self, query: str, max_results: int) -> List[SearchResultItem]: ...
    def _tavily_search(self, query: str, max_results: int) -> List[SearchResultItem]: ...
    def _brave_search(self, query: str, max_results: int) -> List[SearchResultItem]: ...
    def search(self, query: str, max_results: int = 3) -> UnifiedSearchResponse
```
#### 3. Invariants & Operational Rules
* Invariant 1 (Strict Cascade): DuckDuckGo → Tavily → Brave Search.
* Invariant 2 (Key Guarding): Secondary and tertiary tiers must not be executed if API keys are unconfigured.
* Invariant 3 (Total Exhaustion): Returns provider_used="Exhausted" with results=[] without raising unhandled exceptions.
### COMP-08: Structured Telemetry & Cost Accounting Engine
#### 1. Architectural Role & File Location
Target Files: src/telemetry/logger.py & src/telemetry/cost.py
Role: [Certain] Emits RFC 3339-compliant JSON lines to sys.stderr and tracks physical latency alongside shadow cloud API costs.
#### 2. Public Interfaces & Typed Schemas
```python
from typing import Any, Dict, Optional, TextIO

class CostEngine:
    DEFAULT_PRICING: Dict[str, Dict[str, float]]
    def calculate_cost(self, prompt_tokens: int, completion_tokens: int, model_name: str = ...) -> float: ...
    def calculate_tokens_per_second(self, completion_tokens: int, latency_ms: float) -> float: ...

class StructuredLogger:
    def __init__(self, session_id: Optional[str] = None, stream: Optional[TextIO] = None) -> None: ...
    def log_event(
        self,
        event_type: str,
        node: str,
        metrics: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> None: ...
```
#### 3. Invariants & Operational Rules
* Invariant 1 (Single-Line JSON to Stderr): [Certain] Every event must emit a single line of un-nested JSON to sys.stderr terminated with \n (ADR-0013).
* Invariant 2 (Guaranteed Context Propagation): session_id must be present in 100% of emitted records, defaulting to an initialized instance UUID if omitted.
### COMP-09: CLI Application Entrypoint
#### 1. Architectural Role & File Location
* Target File: main.py
* Role: [Certain] Primary executable interface supporting argument parsing, interactive REPL sessions, session resumption, and deterministic POSIX exit codes.
#### 2. Public Interfaces & Typed Schemas
```python
import argparse

def parse_arguments() -> argparse.Namespace: ...
async def main() -> int:
    """Returns POSIX status codes: 0 = success, 1 = error, 2 = security, 3 = circuit break."""
    ...
```
#### 3. Invariants & Operational Rules
* Invariant 1 (POSIX Exit Codes): Explicit exit codes: 0 (Success), 1 (Runtime Error), 2 (Security Violation), 3 (Circuit Break / Iteration Ceiling).
* Invariant 2 (Session Resumption): Support --session-id <UUID> to resume persistent graph execution from .agent_state.db (ADR-0017).

## Verification Cross-Reference Matrix
| Component Identifier | Primary Interface Contact | Unit Verification Target | Integration Verification Target | SLA / Safety Bound |
| :------ | :-------- | :------------------------------------------------------ | :------------------------------------------------------ | :------------------------------------------------------ |
| COMP-01 (Orchestration) | AgentState FSM | test_state_graph.py | test_us01_multistep_query.py | Max 10 turns, Cap ≤4 turns|
|COMP-02 (Model Adapter)	| get_model() Factory	| test_model_adapter.py	| test_us01_multistep_query.py	| Temp = 0.0, 120s Timeout|
|COMP-03 (Circuit Breaker)|	canonical_fingerprint()	| test_loop_detector.py	| test_us02_loop_interception.py|	Strike 3 Interception|
|COMP-04 (FastMCP Server)	|MCPClientManager Stdio	|test_mcp_server.py	|make ci Stdio Stream Audit|	0 bytes on stdout|
|COMP-05 (Docker Sandbox)	|execute_code()	|test_sandbox_security.py	|test_us03_security_containment.py	|5.0s Kill, 256MB Cap, Net None|
|COMP-06 (Database Engine)	|execute_query() / C-Auth|	test_sql_guardrails.py	|test_us03_security_containment.py	|Read-only URI, C-Authorizer|
|COMP-07 (Search Engine)|	search() Cascade|	test_search_fallback.py|	Live Cascade Integration|	3-Tier Fallback to Exhausted|
|COMP-08 (Telemetry)|	log_event() JSON Line|	test_telemetry_schema.py|	make ci Stderr Trace Audit|	RFC 3339 JSON to sys.stderr|
|COMP-09 (CLI Entrypoint)|	main() POSIX Exit|	test_cli_interface.py|	Standalone Execution|	Codes: 0, 1, 2, 3|