# Project: Enterprise MCP Tool-Calling Agent with Observability (Path 2)

**Document Version:** 1.2.0 (Post-Phase 2 Architecture Ratification)
**Target Milestone:** MVP Release (V1)
**Author:** AI Systems Consultant / Forward Deployed Engineering
**Status:** Phase 1 & 2 Complete / Phase 3 Verified / Phase 4 Active

---

## 1. Problem Statement & Success Metrics

### 1.1 Problem Statement

[Certain] Current autonomous ReAct implementations rely on loose, unbounded `while` loops that fail unpredictably in production: they enter cyclic tool-calling loops when tools fail, execute untrusted Python code directly on host runtimes, lack structured audit trails, and fail to manage token costs. This system delivers a deterministic, state-machine-backed agent utilizing the Model Context Protocol (MCP) to isolate tool execution, halt repetitive failure loops, and emit machine-readable telemetry for every state transition.

### 1.2 Target Audience

* **Forward Deployed Engineers (FDEs) & AI Platform Teams:** Requiring a verifiable, observable reference architecture for multi-tool orchestration.
* **Enterprise Data Analysts:** Needing automated, multi-step data retrieval (SQL), synthesis (Python), and external validation (Web Search) without security exposure.

### 1.3 Success Metrics (V1 Key Performance Indicators)

* **Loop Mitigation Rate:** [Certain] 100% of repetitive, identical tool invocations intercepted and halted at strike 3 via SHA-256 argument fingerprinting and commutative SQL AST canonicalization.
* **Containment & Security:** [Certain] 0 unauthorized OS-level operations executed; 100% of destructive SQL commands (`DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `ATTACH`) blocked at both the C-engine parser layer and connection level before query evaluation.
* **Execution Latency (P95):** [Likely] Multi-tool execution chain (2 tool calls + final synthesis) resolves in $\le 8.5$ seconds under standard local Ollama Qwen 2.5 7B inference windows. (Subsystem budget: LLM inference $\le 6.0$s; Docker sandbox execution $\le 2.2$s; Graph routing $\le 0.3$s).
* **Cost Ceilings:** [Certain] Hard-stop abort triggered if any single transaction exceeds $0.05 USD or 10 iterations.
* **Telemetry Coverage:** [Certain] 100% of LLM calls, tool executions, and state routing steps logged with structured JSON to `sys.stderr` containing latency, token counts, and cost metadata.

---

## 2. User Stories & Acceptance Criteria

### US-01: Multi-Step Analytical Query Resolution

*As a Data Analyst, I want the agent to query database metrics and process them using Python, so that I receive verified aggregate calculations without writing manual ETL scripts.*

* **Scenario 1: Successful Multi-Step Execution**
  * **Given:** The agent receives: *"Calculate total CloudEngine revenue and project a 15% increase."*
  * **When:** The LangGraph state machine initiates execution.
  * **Then:** The agent calls `query_database` to fetch data, feeds returned records into `run_python` to compute the 15% delta, and returns the synthesized result.
  * **And:** Total iterations must not exceed 4 steps.

### US-02: Deterministic Loop Interception (Circuit Breaker)

*As a Platform Operations Engineer, I want the system to kill repeated tool calls, so that broken agent logic does not drain budgets or exhaust compute.*

* **Scenario 1: Cyclic Tool-Calling Prevention**
  * **Given:** The agent encounters a tool error or hallucinated parameter set.
  * **When:** The agent requests a tool call whose canonical argument hash matches 2 preceding calls in the same session (including SQL queries with shifted whitespace, case, or inverted commutative equality operators like `1 = id`).
  * **Then:** The system intercepts execution, bypasses the tool, injects a synthetic `ToolMessage` bearing the matching `tool_call_id` into context, and forces an alternate reasoning path without breaking wire protocol.

### US-03: Malicious Execution Containment

*As an InfoSec Compliance Auditor, I want untrusted code execution and SQL injections blocked at the tool interface, so that the host system and data stores remain uncompromised.*

* **Scenario 1: Destructive SQL Interception**
  * **Given:** An agent requests `query_database` with `DROP TABLE product_revenue;` or `DELETE/**/FROM product_revenue`.
  * **When:** The SQLite C-authorizer interceptor processes the statement.
  * **Then:** Execution is rejected immediately with a `Security Violation` message without modifying the database file.
* **Scenario 2: Malicious Python Execution**
  * **Given:** An agent requests `run_python` containing socket calls or filesystem scans.
  * **When:** The isolated container runs with `--network none` and `--read-only`.
  * **Then:** Execution fails at the OS kernel level, and the container is destroyed.

---

## 3. Scope Specification (V1 vs. Out-of-Scope)

| IN SCOPE (V1 MVP) | OUT OF SCOPE (Future Releases) |
| :--- | :--- |
| FastMCP Server via stdio JSON-RPC transport | FastMCP over SSE / HTTP / Unix Sockets |
| LangGraph StateGraph deterministic engine (v1.2.x) | Web UI / Interactive Chat Frontend |
| Tools: `web_search`, `run_python`, `query_database` | Human-in-the-Loop (HITL) pause nodes |
| Schema Resource: `schema://main` | Database write permissions |
| SHA-256 + Commutative SQL AST Loop Detection (`sqlglot`) | Dynamic vector-based tool routing |
| Hardened Docker daemon container sandbox | Distributed multi-agent swarms |
| Telemetry JSON Lines emitted strictly to `sys.stderr` | Distributed OpenTelemetry trace collectors |
| Persistent SQLite WAL Checkpointing (`.agent_state.db`) | Remote cloud database persistence |

---

## 4. Data Models & Schemas

### 4.1 LangGraph State Schema (`AgentState`)

[Certain] The internal system state passed between nodes in the graph execution tree:

```python
class AgentState(TypedDict):
    # Message conversation history including Human, AI, and Tool messages
    messages: Annotated[Sequence[BaseMessage], add_messages]
    # Current loop execution depth
    iteration_count: int
    # Mapping of SHA-256 signatures to their invocation frequency
    tool_call_history: dict[str, int]
    # Run transaction identifier
    session_id: str
```

### 4.2 Tool Call Hash Definition
[Certain] To provide deterministic deduplication across semantically identical calls:
```text
Hash=SHA256(tool_name+":""+canonical_payload(args))
```
Where canonical_payload:
Recursively traverses AST for query_database via sqlglot, sorting commutative binary equality expressions (exp.EQ, exp.NEQ) so that 1 = id and id = 1 produce identical ASTs.
Formats SQL to canonical SQLite dialect.
For general arguments, serializes with json.dumps(args, sort_keys=True, separators=(',', ':')).

### 4.3 Structured Telemetry Event Schema (JSON Lines)
[Certain] Every state transition outputs an un-nested, parsable JSON log event to sys.stderr (ADR-0013):
```json
{
  "timestamp": "2026-10-13T11:45:00.123456+00:00",
  "session_id": "uuid-v4-string",
  "event_type": "llm_completion | tool_execution | circuit_breaker_tripped | system_abort",
  "node": "agent_node | tool_node | force_end_node",
  "metrics": {
    "latency_ms": 1240.50,
    "prompt_tokens": 450,
    "completion_tokens": 82,
    "cost_usd": 0.0001167
  },
  "payload": {
    "tool_name": "query_database",
    "tool_call_id": "call_12345",
    "iteration": 1
  }
}
```

### 4.4 SQLite Target Schema (company_metrics.db)
[Certain] The read-only embedded schema exposed to the agent:
```sql
CREATE TABLE product_revenue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name TEXT NOT NULL,
    quarter TEXT NOT NULL,
    revenue REAL NOT NULL
);
```

### 5. Architectural Resolutions & Concrete Specifications
#### 5.1 Model Runtime, Compute Budget & Timeout Resolution
* Hardware Profile: NVIDIA GeForce RTX 4060 Laptop GPU (8,192 MB GDDR6 physical VRAM).
* Primary Local LLM: qwen2.5:7b-instruct-q4_K_M served via Ollama (Static weights: ~4,400 MB; KV cache: ~1,200 MB).
* Concurrency & Keep-Alive: Enforced OLLAMA_MAX_LOADED_MODELS=2 and keep_alive: -1 to prevent PCIe cold-load penalties.
* Transport Deadline Resolution: MODEL_TIMEOUT=120.0s configured on ChatOpenAI client to accommodate GBNF grammar compilation and WSL2 virtualization TTFT on multi-tool prompts.
* CI Cloud Fallback: gpt-4o-mini activated automatically when Ollama is unreachable and OPENAI_API_KEY is present.

#### 5.2 Code Execution Isolation & Sandbox Resolution
* Isolation Engine: Docker Engine API socket (/var/run/docker.sock).
* Container Parameters: python:3.11-slim, --network none, --memory 256m, --cpus 1.0, --read-only, tmpfs at /tmp:rw,size=16m.
* Execution Timeout: Hard 5.0-second wall-clock termination managed via container lifecycle polling and container.kill().
* Benchmark: P50 execution latency of 1,034.09 ms for analytical tasks.

#### 5.3 Database Access Architecture
* Physical File: Embedded SQLite (company_metrics.db).
* Connection Security: URI connection with mode=ro.
* Engine Interception: C-level sqlite3.Connection.set_authorizer callback rejecting all actions outside SQLITE_SELECT, SQLITE_READ, and SQLITE_FUNCTION.

#### 6. Architectural Decision Records (ADRs)
1. ADR-01: Orchestration Engine Architecture
- Status: Accepted & Binding.
- Decision: Implement LangGraph StateGraph as an explicit Deterministic Finite State Machine (FSM).
2. ADR-02: Tool Communication Protocol
- Status: Accepted & Binding.
- Decision: Standardize on the Model Context Protocol (MCP) using FastMCP via standard I/O (stdio) JSON-RPC 2.0 communication.
3. ADR-03: Code Execution Sandbox Isolation
- Status: Accepted & Binding.
- Decision: Ephemeral Docker containers via /var/run/docker.sock (--network none, 256MB RAM, read-only root, 5s timeout).
4. ADR-04: Local LLM Engine & Quantization Sizing
- Status: Accepted & Binding.
- Decision: Deploy Qwen 2.5 7B Instruct Q4_K_M via Ollama on RTX 4060 GPU.
5. ADR-05: Embedding Model & Context Capacity
- Status: Accepted & Binding.
- Decision: Deploy nomic-embed-text-v1.5 (8,192 token window) via Ollama.
6. ADR-06: Loop Detection & Circuit Breaker Architecture
- Status: Accepted & Binding.
- Decision: Implement deterministic SHA-256 fingerprinting halting execution at strike 3.
7. ADR-07: External Search Infrastructure Resiliency
- Status: Accepted & Binding.
- Decision: Chain of Responsibility multi-provider cascade (DuckDuckGo -> Tavily -> Brave Search).
8. ADR-08: Relational Database Access Architecture
- Status: Accepted & Binding.
- Decision: Embedded SQLite with read-only URI connection strings (mode=ro) and MCP Resource schema exposition.
9. ADR-09: Telemetry & Cost Accounting Architecture
- Status: Accepted & Binding.
- Decision: Un-nested structured JSON telemetry lines incorporating shadow cloud pricing (0.15/0.60 per 1M tokens).
10. ADR-10: Ollama Multi-Model Concurrency & Keep-Alive Policy
- Status: Accepted & Binding.
- Decision: Enforce OLLAMA_MAX_LOADED_MODELS=2 and pass keep_alive: -1.
11. ADR-11: MCP Stdio Client Bridge via langchain-mcp-adapters
- Status: SUPERSEDED BY ADR-0019.
- Reason: Incompatible dependency graph with MCP 2.x and FastMCP 4.x.
12. ADR-12: Resilient GPU Telemetry with Multi-Tier Fallback
- Status: Accepted & Binding.
- Decision: Multi-tier GPU inspection (nvidia-ml-py -> CLI nvidia-smi -> CI Mock).
13. ADR-0013: Stream Demultiplexing for FastMCP and Observability
- Status: Accepted & Binding.
- Decision: Reserve sys.stdout exclusively for JSON-RPC 2.0 frames; route all JSON telemetry strictly to sys.stderr.
14. ADR-0014: SQLite C-Level Authorizer Engine Integration
- Status: Accepted & Binding.
- Decision: Implement sqlite3.Connection.set_authorizer rejecting mutations at C-engine parser evaluation.
15. ADR-0015: Runtime Dependency Harmonization (LTS 2026 Baseline)
- Status: Accepted & Binding.
- Decision: Synchronize stack on modern 2026 releases: langchain-core>=1.6.0, langgraph>=1.2.0, fastmcp>=4.0.0, mcp>=2.0.0, and sqlglot>=30.0.0.
16. ADR-0016: Commutative Domain-Aware AST Loop Sentinel
- Status: Accepted & Binding.
- Context: Minor SQL syntax variations (whitespace, casing, operand order 1 = id vs id = 1) bypassed string-based deduplication.
- Decision: Transform SQL queries with sqlglot AST parsing, sorting commutative binary equality operands before generating canonical digests.
- Traceability: Satisfies US-02 and KPI 1.3 (100% Loop Break Rate).
17. ADR-0017: Persistent State Checkpointing via Async SQLite WAL
- Status: Accepted & Binding.
- Context: Ephemeral memory checkpoints drop session context across process runs and lack crash resilience.
- Decision: Compile the state graph with AsyncSqliteSaver targeting .agent_state.db configured with Write-Ahead Logging (PRAGMA journal_mode=WAL;).
- Traceability: Satisfies Section 3 (Persistence) and Task 5.1 (Session Resumption).
18. ADR-0018: Atomic Partition & Fan-Out Tool Dispatch
- Status: Accepted & Binding.
- Context: Decoupled circuit breaker nodes dropped valid parallel tool calls when a sibling call tripped the strike limit, violating OpenAI wire protocols.
- Decision: Unify circuit breaking and tool execution inside tool_node. Partition calls into safe vs tripped, execute safe calls, synthesize ToolMessage instances for tripped calls, and fulfill 100% of requested tool_call_ids in a single batch.
- Traceability: Satisfies US-02 and preserves OpenAI/Ollama wire compatibility.
19. ADR-0019: Native FastMCP Client Integration
- Status: Accepted & Binding.
- Supersedes: ADR-11.
- Context: langchain-mcp-adapters 0.3.1 broke on mcp 2.0.0 due to the removal of RequestContext, creating a version deadlock with FastMCP 4.x.
- Decision: Utilize native fastmcp.Client with StdioTransport directly in src/agent/mcp_client.py. - Dynamically synthesize Pydantic schemas via pydantic.create_model() to wrap MCP tools as LangChain StructuredTool instances.
- Traceability: Resolves packaging solver deadlocks and eliminates unnecessary third-party adapters.

### 7. Architectural Traceability Cross-Reference

| Architectural Decision	| Direct PRD Requirement / KPI	 | Primary Failure Mode Mitigated|
| :------------------------ | :------------------------- | :---------------------------- |
|ADR-01: StateGraph	| US-01, US-02, KPI 1.3	| Unrecoverable crashes during intermediate tool failures|
|ADR-02: FastMCP	| Scope V1, FDE Standards	| Cascading agent host crashes caused by tool memory leaks|
|ADR-03: Docker Sandbox	| US-03, KPI 1.3 (Security)	| Arbitrary host filesystem deletion and local network scanning|
|ADR-04: Qwen 2.5 7B Q4	| KPI 1.3 (Latency ≤8.5s)	| CUDA Out-of-Memory crashes and PCIe memory bus offloading|
|ADR-05: nomic-embed (8k)	|Section 5.1 (Context Budget)	|Silent truncation of complex multi-table database schemas|
|ADR-0013: Stream Demux	| KPI 1.3 (Telemetry Coverage)|	JSON-RPC parser collapse caused by logging to stdout|
|ADR-0014: C-Authorizer	|US-03 (SQL Guardrails)	|SQL injection bypasses via comments and obfuscated statements|
|ADR-0016: AST Sentinel	|US-02 (Loop Defense)	|Agent loop escapes via commutative predicate inversion|
|ADR-0017: SQLite WAL	|Section 3 (Persistence)	|Conversational state loss during process restart|
|ADR-0018: Atomic Dispatch	| US-02, OpenAI Wire Spec	| HTTP 400 Bad Request caused by missing tool_call_id responses|
|ADR-0019: Native FastMCP	| ADR-02, Section 3	|SAT solver package deadlocks between FastMCP and adapters|