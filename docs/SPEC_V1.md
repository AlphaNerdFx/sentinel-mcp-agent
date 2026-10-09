# Technical Component Specifications (SPEC_V1.md)

**System Target:** Enterprise MCP Tool-Calling Agent with Observability
**Document Version:** 1.0.0 (Release Candidate Specification)
**Tracking PRD:** `agent_system_prd_v1.md`
**Standard:** Production-Grade Interface Contract

---

## Component Index

1. [COMP-01: Orchestration Engine &amp; State Machine](#comp-01-orchestration-engine--state-machine)
2. [COMP-02: Model Provider Adapter](#comp-02-model-provider-adapter)
3. [COMP-03: Tool-Call Loop Detector &amp; Circuit Breaker](#comp-03-tool-call-loop-detector--circuit-breaker)
4. [COMP-04: FastMCP Tool Server &amp; Resource Registry](#comp-04-fastmcp-tool-server--resource-registry)
5. [COMP-05: Docker Container Sandbox Runner](#comp-05-docker-container-sandbox-runner)
6. [COMP-06: Relational Database Access Engine](#comp-06-relational-database-access-engine)
7. [COMP-07: Resilient Multi-Provider Search Engine](#comp-07-resilient-multi-provider-search-engine)
8. [COMP-08: Structured Telemetry &amp; Cost Accounting Engine](#comp-08-structured-telemetry--cost-accounting-engine)
9. [COMP-09: CLI Application Entrypoint](#comp-09-cli-application-entrypoint)

---

### COMP-01: Orchestration Engine & State Machine

#### 1. Architectural Role & File Location

* **Target File:** `src/agent/graph.py` & `src/agent/nodes.py`
* **Role:** [Certain] Implements a Deterministic Finite State Machine (FSM) via LangGraph that coordinates reasoning, tool execution, safety checks, and termination boundaries.

#### 2. Public Interfaces & Typed Schemas

```python
from typing import Annotated, Dict, List, Literal, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    """Immutable state container passed across all graph nodes."""
    messages: Annotated[List[BaseMessage], add_messages]
    iteration_count: int
    tool_call_history: List[str]  # Stores SHA-256 fingerprint strings
    session_id: str

def agent_node(state: AgentState) -> Dict[str, Any]:
    """Invokes the bound LLM, increments iteration_count, and logs telemetry."""
    ...

def tool_execution_node(state: AgentState) -> Dict[str, Any]:
    """Executes requested tool calls through FastMCP client with circuit breaker interception."""
    ...

def force_end_node(state: AgentState) -> Dict[str, Any]:
    """Generates a structured termination notice when the iteration cap is hit."""
    ...

def should_continue(state: AgentState) -> Literal["call_tools", "end", "force_end"]:
    """Conditional routing edge determining next state transition."""
    ...
```

#### 3. Invariants & Operational Rules

Invariant 1 (Loop Cap): [Certain] If state["iteration_count"] >= 10, should_continue must return "force_end". Execution must never cycle back to agent_node.
Invariant 2 (State Append-Only): Message history must use LangGraph's add_messages reducer to ensure that intermediate tool executions are preserved in chronological order.
Invariant 3 (Edge Determinism): A node must never transition directly to the terminal state END while unhandled tool_calls exist on the last message.

#### 4. Failure Modes & Recovery Semantics

Tool Execution Exception: Captured and wrapped inside a ToolMessage(content="Error: ", tool_call_id=call_id). The exception must not crash the orchestrator process.
Context Window Overflow: Intercepted at agent_node. If input tokens exceed 8,000, execution routes to force_end_node with status ContextWindowExhausted.

#### 5. Resource & Performance Budget

Graph Transition Latency: ≤10ms overhead per node transition (excluding model inference time).
State Memory Footprint: ≤2MB total in-memory size per session state.

### COMP-02: Model Provider Adapter

#### 1. Architectural Role & File Location

Target File: src/agent/model_adapter.py
Role: [Certain] Provides an abstract factory that instantiates a tool-bound LLM client, routing to local Ollama by default and falling back to pay-as-you-go cloud APIs in CI environments.

#### 2. Public Interfaces & Typed Schemas

```python
from typing import List, Protocol
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool

class ModelAdapterProtocol(Protocol):
    def get_model(self, tools: List[BaseTool]) -> BaseChatModel:
        """Returns a configured chat model bound to the provided MCP tool schemas."""
        ...

class LocalOllamaAdapter:
    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        model_name: str = "qwen2.5:7b-instruct-q4_K_M",
        temperature: float = 0.0,
    ) -> None: ...
    def get_model(self, tools: List[BaseTool]) -> BaseChatModel: ...

class CloudFallbackAdapter:
    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.0,
    ) -> None: ...
    def get_model(self, tools: List[BaseTool]) -> BaseChatModel: ...
```

#### 3. Invariants & Operational Rules

* Invariant 1 (Deterministic Sampling): [Certain] temperature must be hard-coded to 0.0 across all adapters to enforce deterministic function calling and eliminate token sampling variance.
* Invariant 2 (Automatic CI Fallback): If http://localhost:11434 does not respond to an HTTP health check within 1.0 second, the adapter must look for the OPENAI_API_KEY environment variable and switch to CloudFallbackAdapter. If neither is available, it raises RuntimeEnvironmentError.

#### 4. Failure Modes & Recovery Semantics

CUDA OOM / Service Crash: If the local Ollama process dies during generation, the adapter raises InferenceEngineUnavailableError with instructions to run scripts/check_env.py.

#### 5. Resource & Performance Budget

Initialization Overhead: ≤50ms client instantiation time.

### COMP-03: Tool-Call Loop Detector & Circuit Breaker

#### 1. Architectural Role & File Location

* Target File: src/agent/circuit_breaker.py
* Role: [Certain] Detects repetitive, unproductive tool invocations by computing canonical cryptographic fingerprints of tool call requests.

#### 2. Public Interfaces & Typed Schemas

```python
from typing import Any, Dict, Tuple

class ToolCallCircuitBreaker:
    @staticmethod
    def compute_fingerprint(tool_name: str, args: Dict[str, Any]) -> str:
        """Computes deterministic SHA-256 hash of tool_name + key-sorted JSON args."""
        ...

    @staticmethod
    def inspect_call(
        fingerprint: str,
        history: List[str],
        strike_threshold: int = 3,
    ) -> Tuple[bool, int]:
        """
        Evaluates call history against the threshold.
        Returns: (is_tripped: bool, current_strike_count: int)
        """
        ...
```

#### 3. Invariants & Operational Rules

* Invariant 1 (Canonical Serialization): [Certain] JSON serialization must enforce sort_keys=True, separators=(',', ':'), and convert all numeric types to uniform string representations to ensure semantic equivalency:

```text
SHA256(′query_db:{"limit":10,"table":"sales"}′)==SHA256(′query_db:{"table":"sales","limit":10}′)
```

* Invariant 2 (Strict Interception Boundary): If current_strike_count >= 3, the tool execution must be bypassed. The circuit breaker returns a synthetic system warning message into the state context, forcing the agent to rethink its plan.

#### 4. Failure Modes & Recovery Semantics

Serialization Failure: If tool arguments contain non-serializable objects (e.g., raw binary buffers), the circuit breaker falls back to hashing repr(sorted(args.items())) and logs a serialization warning.

#### 5. Resource & Performance Budget

Hashing Latency: ≤0.5 ms execution time per tool signature check.
Memory Overhead: 64 bytes per fingerprint entry in state history.

### COMP-04: FastMCP Tool Server & Resource Registry

#### 1. Architectural Role & File Location

* Target File: src/server.py
* Role: [Certain] Implements the Model Context Protocol (MCP) server, registering tools and resources and serving them via JSON-RPC 2.0 over standard I/O (stdio).

#### 2. Public Interfaces & Typed Schemas

```python
from fastmcp import FastMCP

mcp = FastMCP(
    name="Enterprise-Tool-Server",
    dependencies=["docker", "duckduckgo-search", "pydantic"],
)

@mcp.resource("schema://main")
def get_db_schema() -> str:
    """Returns relational SQLite database schema as read-only contextual text."""
    ...

@mcp.tool()
def web_search(query: str) -> str:
    """Executes multi-provider web search and returns normalized text."""
    ...

@mcp.tool()
def query_database(sql_query: str) -> str:
    """Executes read-only SQL SELECT queries against product_revenue table."""
    ...

@mcp.tool()
def run_python(code: str) -> str:
    """Executes untrusted Python code inside the Docker sandbox."""
    ...
```

#### 3. Invariants & Operational Rules

Invariant 1 (Stdio Hygiene): [Certain] The server process must never write raw debug text or unformatted prints to sys.stdout. Standard out is strictly reserved for JSON-RPC 2.0 communication frames. Any diagnostic logging must be directed to sys.stderr.
Invariant 2 (MCP Resource Segregation): The database schema must be exposed as a Resource (schema://main), not as a tool call, ensuring clients can attach schema context without burning tool iterations.

#### 4. Failure Modes & Recovery Semantics

Malformed JSON-RPC Message: FastMCP returns standard JSON-RPC error code -32700 (Parse error) or -32600 (Invalid Request) without terminating the server process.

#### 5. Resource & Performance Budget

Process Footprint: ≤60 MB resident set size (RSS) idle memory.
IPC Serialization Overhead: ≤2 ms per JSON-RPC frame round-trip.

### COMP-05: Docker Container Sandbox Runner

#### 1. Architectural Role & File Location

* Target File: src/sandbox/docker_runner.py
* Role: [Certain] Manages ephemeral container lifecycles via the Docker Engine API socket, executing untrusted Python code inside a secure, non-networked environment.

#### 2. Public Interfaces & Typed Schemas

```python
from dataclasses import dataclass
from typing import Optional

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

    def execute_code(self, script_contents: str) -> ExecutionResult:
        """
        Creates, executes, and force-removes an isolated ephemeral container.
        """
        ...
```

#### 3. Invariants & Operational Rules

* Invariant 1 (Network Elimination): [Certain] Container creation must strictly specify network_mode="none". Outbound/inbound socket calls must fail at the kernel level.
* Invariant 2 (Ephemeral Destruction): In the finally block of execute_code, container.remove(force=True) must execute unconditionally to prevent orphaned containers from leaking memory.
* Invariant 3 (Filesystem Lockdown): The container root must be mounted with read_only=True. Writable scratchpad storage is restricted to an in-memory mount: tmpfs={"/tmp": "rw,size=16m"}.

#### 4. Failure Modes & Recovery Semantics

Execution Timeout: If execution exceeds 5.0 seconds, the runner issues container.kill(), sets timed_out=True, and returns exit code 124.
Memory Exhaustion (OOM): If a script allocates >256 MB, the Linux kernel terminates the process with exit code 137. The runner catches this and reports: "Memory limit exceeded (256MB cap)".
Socket Inaccessible: If /var/run/docker.sock is missing, raises DockerDaemonUnavailableError.

#### 5. Resource & Performance Budget

Execution Latency: Container lifecycle (create → start → wait → delete) must complete in ≤800 ms overhead for trivial scripts.
Maximum CPU Footprint: Capped at 1.0 CPU core (nano_cpus=1_000_000_000).

### COMP-06: Relational Database Access Engine

#### 1. Architectural Role & File Location

Target File: src/tools/database.py
Role: [Certain] Provides read-only access to the local SQLite database, enforcing read-only constraints at the filesystem, connection, and query-parser layers.

#### 2. Public Interfaces & Typed Schemas

```python
from typing import List, Dict, Any

class DatabaseEngine:
    def __init__(self, db_path: str = "company_metrics.db") -> None: ...

    def initialize_database(self) -> None:
        """Creates table product_revenue and seeds demo data if missing."""
        ...

    def get_schema(self) -> str:
        """Queries sqlite_master and returns the exact CREATE TABLE DDL."""
        ...

    def execute_query(self, sql_query: str) -> List[Dict[str, Any]]:
        """
        Validates and executes a read-only SELECT query.
        Raises: SecurityViolationError, DatabaseExecutionError
        """
        ...
```

#### 3. Invariants & Operational Rules

Invariant 1 (Read-Only Connection): [Certain] SQLite connection strings must use URI mode: sqlite3.connect(f"file:{db_path}?mode=ro", uri=True).
Invariant 2 (Keyword Gate): Incoming SQL queries must be inspected prior to execution. If any of the tokens ['insert', 'update', 'delete', 'drop', 'alter', 'truncate', 'attach', 'detach'] match a regex boundary check, execution is blocked and raises SecurityViolationError.
Invariant 3 (Row Output Formatting): Query results must return as a list of dictionaries mapping column names to values, serialized to a clean JSON string for the model context.

#### 4. Failure Modes & Recovery Semantics

SQL Syntax Error: Caught and returned as an error string to the agent context: "Database Error: near 'FORM': syntax error". This allows the LLM to self-correct its query on the next turn.

#### 5. Resource & Performance Budget

Query Latency: ≤10ms execution time for analytical queries up to 10,000 rows.

### COMP-07: Resilient Multi-Provider Search Engine

#### 1. Architectural Role & File Location

Target File: src/tools/search.py
Role: [Certain] Implements the Chain-of-Responsibility fallback search pipeline across DuckDuckGo, Tavily, and Brave Search, normalizing responses into a unified Pydantic schema.

### 2. Public Interfaces & Typed Schemas

```python
from typing import List, Literal
from pydantic import BaseModel, HttpUrl

class SearchResultItem(BaseModel):
    title: str
    snippet: str
    source_url: str

class UnifiedSearchResponse(BaseModel):
    provider_used: Literal["DuckDuckGo", "Tavily", "BraveSearch", "Exhausted"]
    query: str
    results: List[SearchResultItem]

    def to_context_string(self) -> str:
        """Formats the search results into a clean context block for the model."""
        ...

class ResilientSearchEngine:
    def __init__(
        self,
        tavily_api_key: Optional[str] = None,
        brave_api_key: Optional[str] = None,
    ) -> None: ...

    def search(self, query: str, max_results: int = 3) -> UnifiedSearchResponse: ...
```

#### 3. Invariants & Operational Rules

Invariant 1 (Strict Cascade Order): [Certain] The search sequence must execute in strict order:
DuckDuckGo (zero-key scrape)
Tavily Search API (if key present and Tier 1 fails with HTTP 429/Timeout)
Brave Search API (if key present and Tier 2 fails)
Invariant 2 (Total Failure Fallback): If all three providers fail or keys are absent, the engine must never raise an unhandled exception. It returns UnifiedSearchResponse(provider_used="Exhausted", query=query, results=[]).

#### 4. Failure Modes & Recovery Semantics

HTTP 429 (Rate Limit): The exception is caught at the provider tier, logged to sys.stderr, and execution automatically cascades to the next tier without delay.

#### 5. Resource & Performance Budget

Search Timeout Ceiling: Max 4.0 seconds network timeout per provider request.

### COMP-08: Structured Telemetry & Cost Accounting Engine

#### 1. Architectural Role & File Location

Target File: src/telemetry/logger.py & src/telemetry/cost.py
Role: [Certain] Emits RFC 3339-compliant, machine-readable JSON logs to sys.stdout and tracks both physical performance and shadow cloud API costs.

#### 2. Public Interfaces & Typed Schemas

```python
from typing import Any, Dict, Literal
from pydantic import BaseModel

class TelemetryMetrics(BaseModel):
    latency_ms: float
    input_tokens: int
    output_tokens: int
    tokens_per_second: float
    shadow_cost_usd: float

class TelemetryEvent(BaseModel):
    timestamp: str  # RFC 3339 format
    session_id: str
    event_type: Literal["llm_completion", "tool_executed", "circuit_break", "force_end"]
    node: str
    metrics: TelemetryMetrics
    payload: Dict[str, Any]

class ShadowCostCalculator:
    # Standard baseline pricing ($0.15/1M input, $0.60/1M output)
    INPUT_RATE_PER_TOKEN: float = 0.15 / 1_000_000
    OUTPUT_RATE_PER_TOKEN: float = 0.60 / 1_000_000

    @classmethod
    def calculate_cost(cls, in_tokens: int, out_tokens: int) -> float: ...

class StructuredLogger:
    @staticmethod
    def emit(event: TelemetryEvent) -> None:
        """Serializes and prints the event to sys.stdout as an un-nested JSON string."""
        ...
```

#### 3. Invariants & Operational Rules

Invariant 1 (Single-Line JSON): [Certain] Every event must be printed as a single line of un-nested JSON terminated with a newline (\n). Multi-line JSON formatting is forbidden to ensure compatibility with standard log collectors.
Invariant 2 (Dual Accounting): Every LLM step must calculate both physical compute metrics (latency_ms, tokens_per_second) and economic metrics (shadow_cost_usd).

#### 4. Failure Modes & Recovery Semantics

Logging Serialization Fault: If payload contains non-serializable objects, the logger falls back to string representations (str(obj)) to guarantee that logging never crashes the host agent.

#### 5. Resource & Performance Budget

Telemetry Formatting Latency: ≤1.0 ms overhead per log emission.

### COMP-09: CLI Application Entrypoint

#### 1. Architectural Role & File Location

Target File: main.py
Role: [Certain] The primary executable command-line interface, providing argument parsing, pipeline setup, and stream routing.

#### 2. Public Interfaces & Typed Schemas

```python
import argparse

def parse_arguments() -> argparse.Namespace:
    """
    Parses CLI flags:
      --query / -q : Analytical question string
      --verbose / -v : Boolean flag toggling telemetry emission to stdout
      --check-env : Boolean flag running hardware validation suite
    """
    ...

def main() -> int:
    """
    Application entrypoint.
    Returns: POSIX exit code (0 = success, 1 = error, 2 = security violation, 3 = circuit break)
    """
    ...
```

#### 3. Invariants & Operational Rules

Invariant 1 (Exit Code Contract): [Certain] The process must terminate with explicit POSIX status codes:

* 0: Successful completion and final response generated.
* 1: General system error or unrecoverable exception.
* 2: Security violation triggered (SQL injection, sandbox compromise attempt).
* 3: Execution terminated by circuit breaker or iteration budget limit.

Invariant 2 (POSIX Stream Routing):

* sys.stdout: Final human-readable response text (or structured JSON if piped).
* sys.stderr: Informational logs, warnings, and error diagnostics.

#### 4. Failure Modes & Recovery Semantics

CLI Interrupt (SIGINT / Ctrl+C): Trapped cleanly. The application terminates active Docker containers, prints "Execution aborted by user", and exits with code 130.

#### 5. Resource & Performance Budget

Application Boot Overhead: ≤400 ms from command invocation to initial prompt dispatch.
Verification Cross-Reference Matrix

| Component Identifier      | Primary Interface Contract | Unit Test Target              | Target SLA / Limit        |
| :------------------------ | :------------------------- | :---------------------------- | :------------------------ |
| COMP-01 (Orchestration)   | AgentState FSM             | test_us01_multistep_query.py  | Max 10 turns              |
| COMP-02 (Model Adapter)   | get_model() Factory        | test_model_adapter.py         | Temp = 0.0                |
| COMP-03 (Circuit Breaker) | inspect_call() SHA-256     | test_loop_detector.py         | Strike 3 Interception     |
| COMP-04 (FastMCP Server)  | JSON-RPC 2.0 stdio         | test_mcp_server.py            | Zero raw prints on stdout |
| COMP-05 (Docker Sandbox)  | execute_code()             | test_sandbox_security.py      | 5s Kill / 256MB Cap       |
| COMP-06 (Database Engine) | execute_query()            | SELECT	test_sql_guardrails.py | Read-only URI mode        |
| COMP-07 (Search Engine)   | search() Cascade           | test_search_fallback.py       | 3-Tier Fallback           |
| COMP-08 (Telemetry)       | emit() JSON Line           | test_telemetry_schema.py      | RFC 3339 Compliant        |
| COMP-09 (CLI Entrypoint)  | main() POSIX Exit          | test_cli_interface.py         | Deterministic Exit Codes  |

### Implementation Sequencing Instructions

**Implementation Order:** When implementing Phase 1 and Phase 2 from `TODO.md`, implement components in order from bottom to top:
**COMP-08** (Telemetry) $\rightarrow$ **COMP-06** (Database) $\rightarrow$ **COMP-05** (Docker) $\rightarrow$ **COMP-07** (Search) $\rightarrow$ **COMP-04** (FastMCP) $\rightarrow$ **COMP-03** (Circuit Breaker) $\rightarrow$ **COMP-02** (Adapter) $\rightarrow$ **COMP-01** (Graph) $\rightarrow$ **COMP-09** (CLI) [Certain].

---

# Technical Component Specifications (SPEC_V1.md)

**System Target:** Enterprise MCP Tool-Calling Agent with Observability
**Document Version:** 1.1.0 (Release Candidate Specification)
**Tracking PRD:** `PRD_V1.md`

---

## Component Index

1. [COMP-01: Orchestration Engine &amp; State Machine](#comp-01-orchestration-engine--state-machine)
2. [COMP-02: Model Provider Adapter](#comp-02-model-provider-adapter)
3. [COMP-03: Tool-Call Loop Detector &amp; Circuit Breaker](#comp-03-tool-call-loop-detector--circuit-breaker)
4. [COMP-04: FastMCP Tool Server &amp; Resource Registry](#comp-04-fastmcp-tool-server--resource-registry)
5. [COMP-05: Docker Container Sandbox Runner](#comp-05-docker-container-sandbox-runner)
6. [COMP-06: Relational Database Access Engine](#comp-06-relational-database-access-engine)
7. [COMP-07: Resilient Multi-Provider Search Engine](#comp-07-resilient-multi-provider-search-engine)
8. [COMP-08: Structured Telemetry &amp; Cost Accounting Engine](#comp-08-structured-telemetry--cost-accounting-engine)
9. [COMP-09: CLI Application Entrypoint](#comp-09-cli-application-entrypoint)

---

### COMP-01: Orchestration Engine & State Machine

* **Target Files:** `src/agent/graph.py` & `src/agent/nodes.py`
* **Public Interface:**
  ```python
  from typing import Annotated, Dict, List, Literal, TypedDict, Any
  from langchain_core.messages import BaseMessage
  from langgraph.graph.message import add_messages

  class AgentState(TypedDict):
      messages: Annotated[List[BaseMessage], add_messages]
      iteration_count: int
      tool_call_history: List[str]
      session_id: str

  def agent_node(state: AgentState) -> Dict[str, Any]: ...
  def tool_execution_node(state: AgentState) -> Dict[str, Any]: ...
  def force_end_node(state: AgentState) -> Dict[str, Any]: ...
  def should_continue(state: AgentState) -> Literal["call_tools", "end", "force_end"]: ...
  ```
* **Invariants:**
    1. If iteration_count >= 10, should_continue must return "force_end".
    2. Message updates must append immutably via the add_messages reducer.
    3. Graph execution overhead must not exceed ≤10ms per node transition.

### COMP-02: Model Provider Adapter
* **Target File:** src/agent/model_adapter.py
* **Public Interface:**
```python
from typing import List, Protocol
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool

class ModelAdapterProtocol(Protocol):
    def get_model(self, tools: List[BaseTool]) -> BaseChatModel: ...

class LocalOllamaAdapter:
    def __init__(self, base_url: str = "http://localhost:11434/v1", model_name: str = "qwen2.5:7b-instruct-q4_K_M", temperature: float = 0.0) -> None: ...
    def get_model(self, tools: List[BaseTool]) -> BaseChatModel: ...

class CloudFallbackAdapter:
    def __init__(self, api_key: str, model_name: str = "gpt-4o-mini", temperature: float = 0.0) -> None: ...
    def get_model(self, tools: List[BaseTool]) -> BaseChatModel: ...
```
* **Invariants:**
    1. temperature must be hard-coded to 0.0 across all implementations.
    2. Automatic failover to CloudFallbackAdapter if local Ollama does not respond to health checks within 1.0 second.

### COMP-03: Tool-Call Loop Detector & Circuit Breaker
* **Target File:** src/agent/circuit_breaker.py
* **Public Interface:**
```python
from typing import Any, Dict, List, Tuple

class ToolCallCircuitBreaker:
    @classmethod
    def normalize_arguments(cls, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]: ...
    @classmethod
    def compute_fingerprint(cls, tool_name: str, args: Dict[str, Any]) -> str: ...
    @classmethod
    def inspect_call(cls, fingerprint: str, history: List[str], strike_threshold: int = 3) -> Tuple[bool, int]: ...
```
* **Invariants:**
    1. SQL tool calls must be parsed into an AST via `sqlglot` and transpiled to canonical dialect formatting before hashing.
    2. Identical tool fingerprints recurring 3 times must trip the breaker and bypass execution.

### COMP-04: FastMCP Tool Server & Resource Registry
* **Target File:** src/server.py
* **Public Interface:**
```python
from fastmcp import FastMCP

mcp = FastMCP(name="Enterprise-Tool-Server")

@mcp.resource("schema://main")
def get_db_schema() -> str: ...

@mcp.tool()
def query_database(sql_query: str) -> str: ...

@mcp.tool()
def run_python(code: str) -> str: ...

@mcp.tool()
def web_search(query: str) -> str: ...
```
* **Invariants**:
    1. `sys.stdout` is strictly reserved for JSON-RPC 2.0 frames (ADR-0013).
    2. All diagnostic, trace, and telemetry logging must be directed to `sys.stderr`.
    3. elational schema must be served strictly as an MCP resource (`schema://main`).

### COMP-05: Docker Container Sandbox Runner
* **Target File:** src/sandbox/docker_runner.py
* **Public Interface:**
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
    def __init__(self, image: str = "python:3.11-slim", memory_limit: str = "256m", cpu_quota: float = 1.0, timeout_seconds: int = 5) -> None: ...
    def execute_code(self, script_contents: str) -> ExecutionResult: ...
```
* **Invariants**:
    1. Containers must run with `network_mode="none"`, `read_only=True`, and temporary scratch space limited to `tmpfs={"/tmp": "rw,size=16m"}`.
    2. Ephemeral destruction must execute in `finally blocks` via `container.remove(force=True)`.
    3. Hard timeout enforcement capped at 5.0 seconds.

### COMP-06: Relational Database Access Engine
* **Target File:** src/tools/database.py
* **Public Interface:**
```python
from typing import List, Dict, Any

class DatabaseEngine:
    def __init__(self, db_path: str = "company_metrics.db") -> None: ...
    def initialize_database(self) -> None: ...
    def get_schema(self) -> str: ...
    def execute_query(self, sql_query: str) -> List[Dict[str, Any]]: ...
```
* **Invariants**:
    1. Physical connections must open in URI read-only mode (`file:...mode=ro`).
    2. The SQLite engine must register a C-level authorizer callback denying all mutation actions outside `SQLITE_SELECT`, `SQLITE_READ`, and `SQLITE_FUNCTION` (ADR-0014).

### COMP-07: Resilient Multi-Provider Search Engine
* **Target File:** src/tools/search.py
* **Public Interface:**
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
    def __init__(self, tavily_api_key: Optional[str] = None, brave_api_key: Optional[str] = None, timeout_seconds: float = 4.0) -> None: ...
    def search(self, query: str, max_results: int = 3) -> UnifiedSearchResponse: ...
```
* **Invariants**:
    1. Strict cascade execution: DuckDuckGo → Tavily → Brave Search.
    2. If all tiers fail, returns `UnifiedSearchResponse(provider_used="Exhausted", results=[])` without raising an unhandled exception.

### COMP-08: Structured Telemetry & Cost Accounting Engine
* **Target File:** src/telemetry/logger.py & src/telemetry/cost.py
* **Public Interface:**
```python
from typing import Any, Dict, Literal
from pydantic import BaseModel

class TelemetryMetrics(BaseModel):
    latency_ms: float
    input_tokens: int
    output_tokens: int
    tokens_per_second: float
    shadow_cost_usd: float

class TelemetryEvent(BaseModel):
    timestamp: str
    session_id: str
    event_type: Literal["llm_completion", "tool_executed", "circuit_break", "force_end", "security_violation"]
    node: str
    metrics: TelemetryMetrics
    payload: Dict[str, Any]

class StructuredLogger:
    @staticmethod
    def emit(event: TelemetryEvent) -> None: ...
```
* **Invariants:**
    1. Events must be serialized as single-line JSON and emitted strictly to `sys.stderr` (ADR-0013).
    2. Dual accounting tracking real compute metrics and shadow commercial API costs.

---

## 4. Git Commit and Tagging Instructions

[Certain] Now that the three master governance files have been updated with complete technical prose, commit the documentation updates and apply the Phase 1 milestone tag:

```bash
# 1. Stage the updated governance specifications
git add HANDOVER.md PRD_V1.md SPEC_V1.md

# 2. Commit the documentation updates
git commit -m "docs: synchronize PRD, SPEC, and HANDOVER with Phase 1 runtime architecture"

# 3. Create the annotated Phase 1 git milestone tag
git tag -a v0.1.0-phase1 -m "Phase 1 Complete: Validated SQLite URI ro, Docker sandbox SLA, search cascade, and FastMCP"

# 4. Verify tag creation
git tag -n