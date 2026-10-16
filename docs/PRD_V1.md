# Project: Sentinel MCP Agent (Enterprise Tool-Calling Agent with Observability)

**Document Version:** 1.3.0 (Post-Phase 4 Architecture & CI/CD Ratification)
**Target Milestone:** Version 1.0.0 (Production Reference Stack)
**Author:** AI Systems Architect / Forward Deployed Engineering
**Status:** Phase 1 (Complete) | Phase 2 (Complete) | Phase 3 (Complete) | Phase 4 (Physically Verified & Signed Off) | Phase 5 (Active)
**Repository Identity:** `sentinel-mcp-agent`
**Security Baseline:** ISO/IEC 25010 Standard / Defense-in-Depth C-Authorizer Sandbox

---

## 1. Problem Statement & Success Metrics

### 1.1 Problem Statement

[Certain] Autonomous ReAct (Reasoning + Acting) implementations deployed across enterprise environments suffer from catastrophic unreliability when executing multi-turn tool calling over unbounded loops:

1. **Unbounded Failure Loops:** When tool execution fails, models enter cyclic retry loops, issuing syntactically varied but semantically identical requests that exhaust compute budgets and token quotas.
2. **Untrusted Code Execution Vulnerabilities:** Executing model-generated Python scripts directly on host operating systems or within un-isolated runtimes exposes the host filesystem to arbitrary deletion, socket exfiltration, and local network scanning.
3. **Database Write Smuggling:** Relying on LLMs to self-police SQL queries or using superficial string blacklists (`DROP`, `DELETE`) fails to prevent SQL injection evasion via inline comments (`DELETE/**/FROM`), stacked statements, or `ATTACH DATABASE` file smuggling.
4. **Transport Pipe Corruption:** Standard logging frameworks emitting unformatted diagnostic text to standard output (`stdout`) interleave with JSON-RPC 2.0 framing over standard I/O (stdio), breaking parser synchronization and causing catastrophic pipe drops.
5. **State Loss on Process Crashes:** In-memory execution state is dropped upon process restarts or runtime failures, preventing conversational resumption and transaction recovery.

[Certain] The Sentinel MCP Agent delivers a deterministic, Finite State Machine (FSM)-backed runtime utilizing the Model Context Protocol (MCP) to isolate tool execution, halt repetitive failure loops via commutative AST canonicalization, contain untrusted execution within non-networked Linux cgroups, and emit RFC 3339-compliant structured JSON telemetry for every state transition.

### 1.2 Target Personas & Use Cases

* **Forward Deployed Engineers (FDEs) & AI Platform Teams:** Requiring a verifiable, observable reference architecture for multi-tool orchestration with deterministic cost controls, reproducible CI/CD pipelines, and zero-trust security perimeters.
* **Enterprise Data & Financial Analysts:** Requiring automated, multi-step data retrieval from relational databases (SQLite), mathematical synthesis via isolated Python sandboxes, and external web validation without exposing internal infrastructure to data exfiltration.

### 1.3 Key Performance Indicators (KPIs & Verification SLAs)

* **KPI 1: Loop Mitigation Rate:** [Certain] 100% of repetitive, semantically identical tool invocations intercepted and halted at Strike 3 via SHA-256 argument fingerprinting and commutative SQL AST canonicalization. (Verified in `tests/unit/agent/test_loop_detector.py` and `tests/e2e/test_us02_loop_interception.py`).
* **KPI 2: Security Containment:** [Certain] Zero unauthorized OS-level operations executed; 100% of destructive SQL commands (`DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `ATTACH`) blocked at both the C-engine authorizer layer and operating system VFS connection level before query evaluation. (Verified in `tests/unit/tools/test_sql_guardrails.py` and `tests/e2e/test_us03_security_containment.py`).
* **KPI 3: Execution Latency (P95 SLA):** [Likely] Multi-tool execution chain (2 tool calls + final analytical synthesis) resolves in $\le 8.5$ seconds under standard local Ollama Qwen 2.5 7B inference windows. Subsystem budget:
  * LLM Inference (TTFT + Generation): $\le 6.0\text{s}$
  * Docker Ephemeral Container Sandbox: $\le 2.2\text{s}$
  * LangGraph FSM State Routing: $\le 0.3\text{s}$
* **KPI 4: Cost Ceiling Enforcement:** [Certain] Hard-stop abort triggered if any single transaction exceeds $0.05 USD (shadow billing calculation) or 10 graph iterations. (Verified in `tests/unit/agent/test_state_graph.py`).
* **KPI 5: Telemetry Coverage & Purity:** [Certain] 100% of LLM calls, tool dispatches, and state transitions emitted strictly as single-line JSON records to `sys.stderr`; exactly zero non-JSON-RPC bytes emitted to `sys.stdout`. (Verified via `make ci` stream segregation audit).

---

## 2. User Stories & Acceptance Criteria

### US-01: Multi-Step Analytical Query Resolution

*As an Enterprise Data Analyst, I want the agent to query database metrics and process them using an isolated Python sandbox, so that I receive verified aggregate calculations without writing manual ETL pipelines.*

* **Scenario 1: End-to-End Analytical Synthesis**
  * **Given:** The agent receives the prompt: *"Calculate total CloudEngine revenue and project a 15% increase."*
  * **When:** The LangGraph state machine initiates execution.
  * **Then:** The agent calls `query_database` to fetch records, feeds returned records into `run_python` inside the Docker sandbox to compute the 15% delta, and returns the synthesized response.
  * **And:** Total iterations must not exceed 4 steps. (Verified in `tests/e2e/test_us01_multistep_query.py`).

### US-02: Deterministic Loop Interception (Circuit Breaker)

*As a Platform Operations Engineer, I want the system to kill repeated tool calls, so that broken agent logic does not drain financial budgets or exhaust compute cycles.*

* **Scenario 1: Commutative Query Duplication Interception**
  * **Given:** The agent encounters a tool error or hallucinated parameter set.
  * **When:** The agent requests a tool call whose canonical argument hash matches 2 preceding calls in the same session (including SQL queries with inverted commutative operators like `1 = id` vs `id = 1`, reordered `AND`/`OR` clauses, or shifted whitespace).
  * **Then:** The system intercepts execution, bypasses the tool, injects a synthetic `ToolMessage` bearing the matching `tool_call_id` into context with content `"CIRCUIT BREAKER TRIGGERED"`, and forces an alternate reasoning path without breaking wire protocol. (Verified in `tests/e2e/test_us02_loop_interception.py`).

### US-03: Malicious Execution Containment

*As an InfoSec Compliance Auditor, I want untrusted code execution and SQL injections blocked at the tool interface, so that host systems and data stores remain uncompromised.*

* **Scenario 1: Destructive SQL Statement Interception**
  * **Given:** An agent requests `query_database` with `DROP TABLE product_revenue;` or `DELETE/**/FROM product_revenue`.
  * **When:** The SQLite C-authorizer interceptor processes the statement.
  * **Then:** Execution is rejected immediately with a `SecurityViolationError`, serialized to a wire-safe refusal string without modifying the database file. (Verified in `tests/e2e/test_us03_security_containment.py`).
* **Scenario 2: Malicious Python Code Sandboxing**
  * **Given:** An agent requests `run_python` containing socket connections (`s.connect(('8.8.8.8', 53))`) or root filesystem write attempts (`open('/root/exploit.txt', 'w')`).
  * **When:** The isolated container runs with `--network none` and `--read-only`.
  * **Then:** Execution fails at the Linux OS kernel level (`Errno 101: Network unreachable` or `Errno 30/13: Read-only filesystem / Permission denied`), and the container is force-destroyed. (Verified in `tests/unit/tools/test_sandbox_security.py` and `tests/e2e/test_us03_security_containment.py`).

---

## 3. Scope Specification (V1 vs. Future Horizons)

| IN SCOPE (V1 Production Baseline)                           | OUT OF SCOPE (Future Horizon Releases)     |
| :---------------------------------------------------------- | :----------------------------------------- |
| FastMCP Server via stdio JSON-RPC 2.0 transport             | FastMCP over SSE, HTTP WebSockets, or gRPC |
| LangGraph StateGraph deterministic FSM                      | Dynamic multi-agent swarm negotiation      |
| Tools: `web_search`, `run_python`, `query_database`   | Human-in-the-Loop (HITL) interactive pause |
| MCP Schema Resource: `schema://main`                      | Relational database mutation permissions   |
| SHA-256 + Commutative SQL AST Deduplication (`sqlglot`)   | Vector semantic loop thresholding          |
| Hardened Docker daemon container sandbox (cgroups v2)       | WebAssembly (WASM) microVM runtimes        |
| Telemetry JSON Lines emitted strictly to `sys.stderr`     | Distributed OpenTelemetry OTLP collectors  |
| Persistent SQLite WAL Checkpointing (`.agent_state.db`)   | Distributed PostgreSQL state persistence   |
| Zero-Config CLI Entrypoint with Session Resumption (`-s`) | Multi-tenant browser frontend UI           |

---

## 4. System Data Models & Schemas

### 4.1 LangGraph State Schema (`AgentState`)

[Certain] The internal immutable state container passed across all graph nodes:

```python
class AgentState(TypedDict):
    """
    [Certain] Immutable state container passed across all LangGraph nodes.
    Enforces add_messages append-only reducer and tracks SHA-256 loop counts.
    """
    messages: Annotated[Sequence[BaseMessage], add_messages]
    iteration_count: int
    tool_call_history: dict[str, int]  # Maps SHA-256 digests to invocation strike counts
    session_id: str
```

#### 4.2 Semantic Tool Call Hash Definition

[Certain] Deterministic deduplication across semantically equivalent invocations:

```text
Digest=SHA256(tool_name+":"+canonical_payload(args))
```

Where canonical_payload enforces:
Bottom-up AST traversal via sqlglot.transform.
Normalization of commutative binary equality (exp.EQ, exp.NEQ).
Normalization of relational inversion operators (exp.GT, exp.LT, exp.GTE, exp.LTE).
Lexicographical sorting of commutative logical junctions (exp.And, exp.Or).
Compact JSON serialization (json.dumps(..., sort_keys=True, separators=(',', ':'))).

#### 4.3 Structured Telemetry Event Schema (JSON Lines)

[Certain] Every state transition emits an un-nested, parsable JSON record to sys.stderr:

```json
{
  "timestamp": "2026-10-16T18:45:00.123456+00:00",
  "session_id": "fc8ea644-626d-410d-a458-d5be0f7368f4",
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

#### 4.4 SQLite Target Schema (company_metrics.db)

[Certain] Embedded relational database schema exposed to the agent:

```sql
CREATE TABLE product_revenue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name TEXT NOT NULL,
    quarter TEXT NOT NULL,
    revenue REAL NOT NULL
);
```

### 5. Formal Architectural Decision Records (ADRs)

#### ADR-0001: Orchestration Engine Architecture

* Status: Accepted & Binding.
* Context: Autonomous ReAct loops implemented with unbounded while loops crash unpredictably and lose state history during intermediate failures.
* Decision: Implement LangGraph StateGraph as an explicit Deterministic Finite State Machine (FSM).
* ISO/IEC 25010 Quality Impact: (+) Reliability (Fault Tolerance), (+) Maintainability (Analyzability).

#### ADR-0002: Tool Communication Protocol

* Status: Accepted & Binding.
* Context: Monolithic in-process tool binding couples tools to the agent host, causing host crashes during tool memory leaks.
* Decision: Standardize on the Model Context Protocol (MCP) using FastMCP via standard I/O (stdio) JSON-RPC 2.0 communication.
* ISO/IEC 25010 Quality Impact: (+) Maintainability (Modularity), (+) Reliability (Maturity).

#### ADR-0003: Code Execution Sandbox Isolation

* Status: Accepted & Binding.
* Context: Executing arbitrary Python code on host runtimes allows host filesystem tampering and network socket scanning.
* Decision: Deploy ephemeral Docker containers via /var/run/docker.sock (--network none, --memory 256m, --cpus 1.0, --read-only, tmpfs at /tmp:rw,size=16m, 5.0s timeout).
* ISO/IEC 25010 Quality Impact: (+) Security (Confidentiality, Integrity), (-) Performance (Startup Latency).

#### ADR-0004: Local LLM Engine & Sizing

* Status: Accepted & Binding.
* Context: Cloud-only inference introduces latency, financial burn, and data leakage for internal enterprise analytics.
* Decision: Standardize on qwen2.5:7b-instruct-q4_K_M served via Ollama on an NVIDIA RTX 4060 GPU baseline.
* ISO/IEC 25010 Quality Impact: (+) Security (Data Sovereignty), (+) Performance (Inference Cost).

#### ADR-0005: Embedding Model & Context Budget

* Status: Accepted & Binding.
* Context: Small embedding windows silently truncate complex multi-table relational database DDL schemas.
* Decision: Deploy nomic-embed-text-v1.5 (8,192 token window) via Ollama.
* ISO/IEC 25010 Quality Impact: (+) Functional Suitability (Completeness).

#### ADR-0006: Loop Detection & Circuit Breaker Thresholds

* Status: Accepted & Binding.
* Context: Stochastic agents enter cyclic loops when tools return unexpected formats or errors.
* Decision: Enforce deterministic Strike 3 circuit breaking based on argument fingerprint digests.
* ISO/IEC 25010 Quality Impact: (+) Reliability (Fault Tolerance).

#### ADR-0007: Resilient Search Infrastructure

* Status: Accepted & Binding.
* Context: External web search endpoints experience intermittent rate limits (HTTP 429) and outages.
* Decision: Implement a 3-tier Chain-of-Responsibility fallback cascade: DuckDuckGo (zero-key) → Tavily (authenticated) → Brave Search (authenticated) → Exhausted Null Object.
* ISO/IEC 25010 Quality Impact: (+) Reliability (Recoverability), (+) Performance (Cost Optimization).

#### ADR-0008: Relational Database Access Architecture

* Status: Accepted & Binding.
* Context: Giving write permissions or raw socket access to database engines enables prompt injection attacks to delete data.
* Decision: Deploy embedded SQLite with read-only URI strings (file:company_metrics.db?mode=ro) and MCP resource exposition (schema://main).
* ISO/IEC 25010 Quality Impact: (+) Security (Integrity).

#### ADR-0009: Telemetry & Shadow Cost Accounting

* Status: Accepted & Binding.
* Context: Local model inference obscures what the analytical workload would cost on commercial APIs.
* Decision: Calculate dual metrics for every turn: physical hardware latency/throughput alongside shadow cloud pricing (0.15/0.60 per 1M tokens).
* ISO/IEC 25010 Quality Impact: (+) Maintainability (Analyzability).

#### ADR-0010: Ollama Model Residency & Keep-Alive Policy

* Status: Accepted & Binding.
* Context: Ollama cold-unloading models between turns introduces 4–8 second PCIe offloading penalties.
* Decision: Enforce OLLAMA_MAX_LOADED_MODELS=2 and pass keep_alive: -1 in all inference payloads.
* ISO/IEC 25010 Quality Impact: (+) Performance (Time Behavior).

#### ADR-0011: MCP Stdio Client Bridge via langchain-mcp-adapters

* Status: SUPERSEDED BY ADR-0019.
* Reason: Upstream packaging conflict between langchain-mcp-adapters and MCP 2.x breaking symbols.

#### ADR-0012: Resilient GPU Telemetry with Multi-Tier Fallback

* Status: Accepted & Binding.
* Context: NVML bindings crash in containerized or headless CI runners lacking physical GPUs.
* Decision: Multi-tier GPU inspection cascade (nvidia-ml-py → CLI nvidia-smi → CI Mock).
* ISO/IEC 25010 Quality Impact: (+) Portability (Adaptability).

#### ADR-0013: Stream Demultiplexing for FastMCP and Observability

* Status: Accepted & Binding.
* Context: Standard print() statements to stdout corrupt JSON-RPC 2.0 framing, crashing stdio clients with JSONDecodeError.
* Decision: Reserve sys.stdout exclusively for JSON-RPC 2.0 transport frames; route all diagnostic telemetry, audit events, and logging strictly to sys.stderr.
* ISO/IEC 25010 Quality Impact: (+) Reliability (Maturity), (+) Maintainability (Modularity).

#### ADR-0014: SQLite C-Level Authorizer Engine Integration

* Status: Accepted & Binding.
* Context: Application-level regex or AST filters are bypassed by SQL injection obfuscation (e.g., DELETE/**/FROM).
* Decision: Register sqlite3.Connection.set_authorizer at the C-engine byte-code compilation layer, denying all operations outside SQLITE_SELECT, SQLITE_READ, and SQLITE_FUNCTION.
* ISO/IEC 25010 Quality Impact: (+) Security (Integrity).

#### ADR-0015: Runtime Dependency Harmonization (LTS 2026 Baseline)

* Status: Accepted & Binding.
* Context: Pre-2026 agent packages suffered from incompatible solver graphs.
* Decision: Standardize on LTS releases: langchain-core>=1.6.0, langgraph>=1.2.0, fastmcp>=4.0.0, mcp>=2.0.0, and sqlglot>=30.0.0.
* ISO/IEC 25010 Quality Impact: (+) Maintainability.

#### ADR-0016: Commutative Domain-Aware AST Loop Sentinel

* Status: Accepted & Binding.
* Context: Syntactic variations (e.g., 1 = id vs id = 1, swapped AND clauses) bypassed string hashing.
* Decision: Canonicalize queries via sqlglot AST traversal using expression.transform, commuting binary equality, logical junctions, and relational inversions before SHA-256 fingerprinting.
* ISO/IEC 25010 Quality Impact: (+) Reliability (Fault Tolerance).

#### ADR-0017: Persistent State Checkpointing via Async SQLite WAL

Status: Accepted & Binding.
Context: In-memory checkpoints lose conversational history upon process crash.

* Decision: Bind AsyncSqliteSaver targeting .agent_state.db configured with Write-Ahead Logging (PRAGMA journal_mode=WAL;).
* ISO/IEC 25010 Quality Impact: (+) Reliability (Recoverability).

#### ADR-0018: Atomic Partition & Fan-Out Tool Dispatch

* Status: Accepted & Binding.
* Context: Detached circuit-breaker nodes dropped non-tripped sibling tool calls, causing HTTP 400 Bad Request: missing tool_call_id from model providers.
* Decision: Unify circuit breaking and dispatch inside tool_node: partition calls into safe vs tripped, execute safe calls, synthesize ToolMessage instances for tripped calls, and fulfill 100% of requested IDs in a single turn.
* ISO/IEC 25010 Quality Impact: (+) Reliability (Fault Tolerance), (+) Compatibility.

#### ADR-0019: Native FastMCP Client Integration

* Status: Accepted & Binding (Supersedes ADR-0011).
* Context: Dependency solver deadlock between mcp<2 and fastmcp-slim>=4.
* Decision: Purge third-party adapters; implement native MCPClientManager using fastmcp.Client with StdioTransport and dynamic Pydantic schema synthesis (create_model()).
* ISO/IEC 25010 Quality Impact: (+) Maintainability, (+) Portability.
