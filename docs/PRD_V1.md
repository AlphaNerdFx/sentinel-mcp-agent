# Project: Enterprise MCP Tool-Calling Agent with Observability (Path 2)

**Document Version:** 1.0.0
**Target Milestone:** MVP Release (V1)
**Author:** AI Systems Consultant
**Status:** Approved for Implementation

---

## 1. Problem Statement & Success Metrics

### 1.1 Problem Statement

[Certain] Current autonomous ReAct implementations rely on loose, unbounded `while` loops that fail unpredictably in production: they enter cyclic tool-calling loops when tools fail, execute untrusted Python code directly on host runtimes, lack structured audit trails, and fail to manage token costs. [Certain] This system delivers a deterministic, state-machine-backed agent utilizing the Model Context Protocol (MCP) to isolate tool execution, halt repetitive failure loops, and emit machine-readable telemetry for every state transition.

### 1.2 Target Audience

* **Forward Deployed Engineers (FDEs) & AI Platform Teams:** Requiring a verifiable, observable reference architecture for multi-tool orchestration.
* **Enterprise Data Analysts:** Needing automated, multi-step data retrieval (SQL), synthesis (Python), and external validation (Web Search) without security exposure.

### 1.3 Success Metrics (V1 Key Performance Indicators)

* **Loop Mitigation Rate:** [Certain] 100% of repetitive, identical tool invocations intercepted and halted at strike 3 via SHA-256 argument fingerprinting.
* **Containment & Security:** [Certain] 0 unauthorized OS-level operations executed; 100% of destructive SQL commands (`DROP`, `DELETE`, `UPDATE`, `INSERT`) blocked before engine evaluation.
* **Execution Latency (P95):** [Likely] Multi-tool execution chain (2 tool calls + final synthesis) resolves in $\le 8.5$ seconds under standard OpenAI API response windows.
* **Cost Ceilings:** [Certain] Hard-stop abort triggered if any single transaction exceeds $0.05 USD or 10 iterations.
* **Telemetry Coverage:** [Certain] 100% of LLM calls, tool executions, and state routing steps logged with structured JSON containing latency, token counts, and cost metadata.

---

## 2. User Stories & Acceptance Criteria

### US-01: Multi-Step Analytical Query Resolution

*As a Data Analyst,**I want the agent to query database metrics and process them using Python,**So that I receive verified aggregate calculations without writing manual ETL scripts.*

* **Scenario 1: Successful Multi-Step Execution**
  * **Given:** The agent receives the input: *"Calculate total CloudEngine revenue and project a 15% increase."*
  * **When:** The LangGraph state machine initiates execution.
  * **Then:** The agent must call `query_database` to fetch data, feed the returned records into `run_python` to compute the 15% delta, and return the synthesized result.
  * **And:** Total iterations must not exceed 4 steps.

### US-02: Deterministic Loop Interception (Circuit Breaker)

*As a Platform Operations Engineer,**I want the system to kill repeated identical tool calls,**So that broken agent logic does not drain API budgets or exhaust infrastructure resources.*

* **Scenario 1: Cyclic Tool-Calling Prevention**
  * **Given:** The agent encounters a tool error or hallucinated parameter set.
  * **When:** The agent requests a tool call whose SHA-256 signature matches 2 preceding calls in the same session.
  * **Then:** The system intercepts the call, bypasses physical execution, injects a `Circuit Breaker Triggered` message into the context window, and forces an alternate reasoning path.

### US-03: Malicious Execution Containment

*As an InfoSec Compliance Auditor,**I want untrusted code execution and SQL injections blocked at the tool interface,**So that the host system and data stores remain uncompromised.*

* **Scenario 1: Destructive SQL Interception**
  * **Given:** An agent requests `query_database` with `DROP TABLE product_revenue;`.
  * **When:** The tool input validation interceptor processes the SQL string.
  * **Then:** Execution is rejected immediately with a `Security Violation` message without querying the database engine.
* **Scenario 2: Malicious Python Execution**
  * **Given:** An agent requests `run_python` containing `import os; os.system('ls')`.
  * **When:** The AST/token safety guard parses the string.
  * **Then:** Execution aborts immediately, and the process is killed.

---

## 3. Scope Specification (V1 vs. Out-of-Scope)

| SCOPE MATRIX |
| IN SCOPE (V1 MVP) | OUT OF SCOPE (Future Releases) |
| FastMCP Server via stdio transport | FastMCP over SSE / HTTP |
| LangGraph StateGraph deterministic engine | Web UI / Chat Frontend (CLI) |
| Tools: web_search, run_python, query_database | Human-in-the-Loop (HITL) UI |
| Schema Resource: schema://main | Database write permissions |
| SHA-256 Tool Call Loop Detection | Dynamic vector tool routing |
| Subprocess execution with 5s hard timeout | Multi-agent negotiation loops |
| Structured JSON telemetry output | Distributed trace backends |

---

## 4. Data Models & Schemas

### 4.1 LangGraph State Schema (`AgentState`)

[Certain] The internal system state passed between nodes in the graph execution tree:

```python
class AgentState(TypedDict):
    # Message conversation history including Human, AI, and Tool messages
    messages: Annotated[List[BaseMessage], add_messages]
    # Current loop execution depth
    iteration_count: int
    # History of computed SHA-256 hashes of executed tool signatures
    tool_call_history: List[str]
    # Run transaction identifiers
    session_id: str
```

### 4.2 Tool Call Hash Definition

[Certain] To provide deterministic deduplication, tool signatures must be hashed using the following canonical format:

```
Hash = SHA256 (tool_name + ":"" + canonical_json(args) )
```

Where canonical_json enforces key sorting and whitespace stripping.

### 4.3 Structured Telemetry Event Schema (JSON)

[Certain] Every state transition must output an un-nested, parsable JSON log event to stdout:

```json
{
  "timestamp": "2026-10-05T11:45:00Z",
  "session_id": "uuid-v4-string",
  "event_type": "llm_call | tool_executed | loop_detected | system_abort",
  "node": "agent | tools | force_end",
  "metrics": {
    "latency_ms": 1240.50,
    "input_tokens": 450,
    "output_tokens": 82,
    "estimated_cost_usd": 0.000116
  },
  "payload": {
    "tool_name": "query_database",
    "status": "success | error | blocked"
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

## 5. Edge Cases & Failure States

+------------------------+------------------------------------+-------------------------------------------+
| Failure State          | Trigger Condition                  | System Recovery Action                    |
+------------------------+------------------------------------+-------------------------------------------+
| Tool Loop Strike 1-2   | Identical tool call hash seen 1-2x | Normal tool execution; hash recorded.     |
| Tool Loop Strike 3     | Identical tool call hash seen 3x   | Intercept call; inject ToolMessage alert. |
| Runaway Reasoning      | iteration_count >= 10              | Force route to `force_end` node; halt.    |
| Python Timeout         | run_python execution > 5000ms      | SIGKILL subprocess; return timeout error. |
| Tool Exception         | Python/SQL syntax error            | Return traceback as ToolMessage string.   |
| Model Context Overflow | Context length > 128k tokens       | Abort execution; emit alert log.          |
+------------------------+------------------------------------+-------------------------------------------+

* Subprocess Memory Bomb: If untrusted Python attempts to allocate unbounded RAM (e.g., [0] * 10**9), [Certain] the OS subprocess runner enforces a 256MB virtual memory cap (RLIMIT_AS), causing an immediate memory error returned to the agent context instead of crashing the host process.

## 6. Architectural Resolutions & Concrete Specifications

### 6.1 Model Runtime, Compute Budget & Cost Telemetry Resolution

* **Selected Hardware Profile:** [Certain] NVIDIA GeForce RTX 4060 Laptop GPU (8,192 MB GDDR6 physical VRAM, 128-bit memory bus).
* **Primary LLM Engine:** [Certain] `qwen2.5:7b-instruct` served locally via Ollama, quantized to `Q4_K_M` (4-bit Medium).
  * *Static Weights Footprint:* 4,400 MB VRAM.
  * *Context Architecture:* 8,192 token context window with 16-bit unquantized Key-Value (KV) cache consuming ~1,200 MB VRAM.
* **Primary Embedding Engine:** [Certain] `nomic-embed-text:v1.5` served locally via Ollama.
  * *Static Weights Footprint:* 280 MB VRAM.
  * *Context Capacity:* Native 8,192 tokens (eliminating truncation errors on extensive database schemas).
* **Operating Headroom Allocation:**
  * *System & Display Server Reserve:* 800 MB VRAM.
  * *CUDA Runtime / cuBLAS Buffers:* 500 MB VRAM.
  * *Calculated Total Allocation:* 7,180 MB VRAM (Reserving ~1,012 MB safety margin to prevent host memory thrashing).
* **Inference Abstraction & CI/CD Strategy:**
  * [Certain] Core agent architecture implements an abstract `ModelProviderAdapter` interface.
  * *Local Development:* Routes to `http://localhost:11434/v1` (Ollama).
  * *Continuous Integration (CI):* GitHub Actions environments lack GPUs. The adapter detects the absence of local Ollama instances and falls back to pay-as-you-go cloud endpoints (such as Groq or OpenAI) via the `OPENAI_API_KEY` repository secret.
* **Telemetry Accounting Metric:**
  * [Certain] Telemetry emits physical metrics (`tokens_per_second`, `duration_ms`, `input_tokens`, `output_tokens`).
  * [Certain] Shadow Cost Calculation: Local execution calculates a simulated cloud financial impact using standard commercial rates ($0.15 / 1M prompt tokens, $0.60 / 1M completion tokens) to ensure telemetry parity between local and cloud-hosted runs.

### 6.2 Code Execution Isolation & Sandbox Resolution

* **Isolation Mechanism:** [Certain] Local Docker Daemon Socket integration (`/var/run/docker.sock` on Linux/macOS/WSL2; `npipe:////./pipe/docker_engine` on Windows host).
* **Execution Container:** Ephemeral, disposable container spawned from `python:3.11-slim`.
* **Security & Operational Constraints:**
  * *Network Topology:* Complete network isolation enforced (`--network none`). Zero outbound/inbound socket permissions.
  * *Memory Ceiling:* Hard limit set to 256 MB (`--memory 256m`, `--memory-swap 256m`). Any script attempting memory-exhaustion bombs triggers an immediate kernel Out-Of-Memory termination (`ExitCode 137`).
  * *Compute Quota:* Strictly constrained to 1.0 CPU Core (`--cpus 1.0`).
  * *Filesystem Topology:* Root filesystem mounted as read-only (`--read-only`). A temporary scratchpad directory is mounted in RAM at `/tmp` with a 16 MB maximum size (`--tmpfs /tmp:rw,size=16m`).
  * *Execution Timeout:* Hard 5-second wall-clock termination managed by container lifecycle polling. If execution exceeds 5 seconds, the container is forcibly terminated (`docker kill`) and purged (`docker rm -f`).
* **Failure Handling:**
  * If the Docker daemon is unreachable, the system must not fall back to un-sandboxed host execution. It must immediately halt execution and return: `"Execution Fault: Docker isolation daemon unavailable. Aborting for system safety."`

### 6.3 External Search Resiliency & Normalization Resolution

* **Design Pattern:** [Certain] Chain of Responsibility Multi-Provider Fallback to prevent Single Sources of Failure (SSOF).
* **Cascade Hierarchy:**
  1. *Tier 1 (Zero-Key Primary):* `DuckDuckGo Search` (Scraped API via `duckduckgo_search`). Used for local testing and zero-cost query resolution.
  2. *Tier 2 (Secondary API Fallback):* `Tavily Search API` (Authenticated via `TAVILY_API_KEY`). Automatically activated if Tier 1 raises an HTTP 429 (Rate Limit), anti-bot challenge, or network socket timeout.
  3. *Tier 3 (Tertiary API Fallback):* `Brave Web Search API` (Authenticated via `BRAVE_API_KEY`). Activated if Tier 2 quota is exhausted or encounters HTTP 5xx server faults.
* **Output Normalization Standard:**
  * [Certain] Raw search payloads from all providers are transformed into a strict Pydantic model (`UnifiedSearchResponse`) before entering the agent context window:
    ```python
    class SearchResultItem(BaseModel):
        title: str
        snippet: str
        source_url: str

    class UnifiedSearchResponse(BaseModel):
        provider_used: Literal["DuckDuckGo", "Tavily", "BraveSearch", "Exhausted"]
        query: str
        results: List[SearchResultItem]
    ```
* **Graceful Degradation:**
  * If all three providers fail or keys are absent, the search engine returns an empty `UnifiedSearchResponse` with `provider_used="Exhausted"`, injecting an explicit context message: `"All search providers unavailable. Reason using existing context."` The agent process does not terminate with an unhandled exception.

<!-- APPEND THE FOLLOWING CONTENT TO THE END OF agent_system_prd_v1.md -->

---

### 7. Architectural Decision Records (ADRs)

#### ADR-01: Orchestration Engine Architecture

* **Status:** [Certain] Accepted & Binding.
* **Context:** The agent requires a coordination layer to handle reasoning, tool dispatch, error inspection, and multi-turn loops without losing conversational state.
* **Decision:** Implement **LangGraph StateGraph** as an explicit Deterministic Finite State Machine (FSM).
* **Traceability:** Satisfies **US-01** (Multi-Step Execution) and **KPI 1.3** (Loop Mitigation Rate).
* **Alternatives Evaluated & Rejected:**
  * *Naive Python `while` Loop:* [Certain] Rejected due to lack of checkpointing, high risk of unhandled state corruption during tool failures, and inability to dynamically branch into dedicated recovery nodes.
  * *Legacy LangChain `AgentExecutor`:* [Certain] Rejected due to its black-box design, which hides execution steps and prevents inserting custom circuit-breaker logic between reasoning and execution phases.
* **Accepted Operational Trade-off:** Requires writing explicit typed state schemas (`AgentState`) and defining formal routing logic for each transition rather than relying on rapid, unstructured scripting.

---

#### ADR-02: Tool Communication Protocol

* **Status:** [Certain] Accepted & Binding.
* **Context:** Tools must be exposed to the agent framework through an interface that prevents process-level cascading failures and supports polyglot environments.
* **Decision:** Standardize on the **Model Context Protocol (MCP)** using **FastMCP** via standard input/output (`stdio`) JSON-RPC 2.0 communication.
* **Traceability:** Satisfies **Section 3 Scope** (Protocol Compliance) and the Forward Deployed Engineer (FDE) integration standard.
* **Alternatives Evaluated & Rejected:**
  * *Direct In-Memory Python Functions:* [Certain] Rejected because in-memory binding tightly couples tool execution to the agent process; an unhandled exception or memory leak in a tool threatens the stability of the entire agent host.
  * *Standalone REST/OpenAPI Microservices:* [Certain] Rejected due to unnecessary local infrastructure overhead: managing port allocation, handling local TLS certificates, and adding HTTP networking latency to every local tool invocation.
* **Accepted Operational Trade-off:** Introduces process lifecycle management for child processes and requires serializing and deserializing all tool inputs and outputs into JSON-RPC 2.0 strings.

---

#### ADR-03: Code Execution Sandbox Isolation

* **Status:** [Certain] Accepted & Binding.
* **Context:** The agent synthesizes and executes arbitrary Python code for mathematical operations, creating severe host security and data integrity risks.
* **Decision:** Orchestrate isolated execution using ephemeral containers via the **Local Docker Daemon Socket** (`/var/run/docker.sock`), configuring containers with disabled networking (`--network none`), a 256 MB RAM limit, a 1.0 CPU quota, a read-only root filesystem, and a 5-second execution timeout.
* **Traceability:** Satisfies **US-03** (Malicious Execution Containment) and **KPI 1.3** (Zero Host Compromise).
* **Alternatives Evaluated & Rejected:**
  * *In-Process `exec()` with String Blacklists:* [Certain] Rejected because string filters are trivially bypassed using Python dynamic class traversal (e.g., accessing base object subclasses to instantiate system subprocesses).
  * *Native Subprocess Execution (`subprocess.run`):* [Certain] Rejected because child processes inherit host user permissions, leaving `.env` credential files, local filesystems, and host networks fully exposed to generated code.
* **Accepted Operational Trade-off:** Introduces a dependency on a running local Docker daemon, adds ~400ms–800ms of container creation latency per run, and requires appropriate user permissions to access the Docker socket.

---

#### ADR-04: Local LLM Engine & Quantization Sizing

* **Status:** [Certain] Accepted & Binding.
* **Context:** The system must run on an RTX 4060 Laptop GPU with an **8,192 MB physical VRAM limit**, maintaining high JSON formatting accuracy and function-calling reliability without spilling into system RAM.
* **Decision:** Deploy **Qwen 2.5 7B Instruct**, quantized to **Q4_K_M** (4-bit medium), served locally via Ollama.
* **Traceability:** Satisfies **KPI 1.3** (Latency $\le 8.5$s) and **Section 6.1** (Compute Footprint).
* **Alternatives Evaluated & Rejected:**
  * *Llama 3.2 3B Instruct:* [Likely] Rejected because sub-7B models exhibit higher failure rates on the Berkeley Function Calling Leaderboard (BFCL), frequently emitting malformed JSON or dropping required arguments during multi-tool execution.
  * *Llama 3.1 8B Instruct:* [Certain] Rejected because its static weight size (4.9 GB) combined with an 8k context Key-Value cache (1.8 GB) and system display servers pushes VRAM usage beyond 8.0 GB, causing performance drops from memory offloading to system RAM.
* **Accepted Operational Trade-off:** 4-bit quantization slightly degrades open-ended creative language capability, but preserves structured instruction-following and tool-use accuracy.

---

#### ADR-05: Embedding Model & Context Capacity

* **Status:** [Certain] Accepted & Binding.
* **Context:** Unstructured data, search snippets, and database schemas must be vectorized without silent text truncation on long technical inputs.
* **Decision:** Deploy **nomic-embed-text-v1.5** (supporting an **8,192 token context window**) via Ollama, utilizing ~280 MB of VRAM.
* **Traceability:** Satisfies **Section 6.1** (Operating Headroom Allocation) and schema-retrieval fidelity.
* **Alternatives Evaluated & Rejected:**
  * *`all-MiniLM-L6-v2` or `bge-small-en-v1.5`:* [Certain] Rejected due to their restrictive 256/512 token limits; relational database schemas with multiple tables or column comments exceed 512 tokens and are silently truncated during indexing.
  * *Proprietary Cloud Embeddings (`text-embedding-3-small`):* [Certain] Rejected because external API calls add network latency and ongoing billing dependencies to what should be an offline-capable, local indexing loop.
* **Accepted Operational Trade-off:** Consumes ~280 MB of the shared 8 GB VRAM budget alongside the primary LLM.

---

#### ADR-06: Loop Detection & Circuit Breaker Architecture

* **Status:** [Certain] Accepted & Binding.
* **Context:** Agents entering error states frequently repeat the exact same failing tool invocation, exhausting API budgets and token limits without resolving the task.
* **Decision:** Implement deterministic **SHA-256 fingerprinting** of canonicalized, key-sorted tool arguments, automatically halting execution if identical signatures recur three times.
* **Traceability:** Satisfies **US-02** (Loop Interception) and **KPI 1.3** (100% Repetitive Loop Mitigation).
* **Alternatives Evaluated & Rejected:**
  * *Relying Exclusively on an Iteration Cap (e.g., 10 turns):* [Certain] Rejected because a basic iteration limit allows an agent to burn up to 10 full turns of token context before failing, wasting time and budget without attempting recovery.
  * *Secondary LLM Critic Nodes:* [Certain] Rejected because running an evaluation LLM after every step doubles total token consumption and latency while relying on the same non-deterministic reasoning that caused the loop.
* **Accepted Operational Trade-off:** Requires strict JSON canonicalization (sorting keys and stripping whitespace) prior to hashing so that semantically identical arguments generate matching fingerprints.

---

#### ADR-07: External Search Infrastructure Resiliency

* **Status:** [Certain] Accepted & Binding.
* **Context:** Web search tools depend on third-party services that can fail due to anti-bot scraping protections, rate limits, or quota exhaustion.
* **Decision:** Implement a **Chain of Responsibility multi-provider cascade** (`DuckDuckGo` $\rightarrow$ `Tavily` $\rightarrow$ `Brave Search`), mapping all provider responses into a unified Pydantic data model (`UnifiedSearchResponse`).
* **Traceability:** Satisfies **Section 6.3** (Eliminating Single Sources of Failure) and CI/CD test suite stability.
* **Alternatives Evaluated & Rejected:**
  * *Scraped DuckDuckGo Exclusively:* [Certain] Rejected because scraping endpoints frequently trigger HTTP 429 rate limits and anti-bot blocks on cloud CI runners (like GitHub Actions), causing automated test suites to fail unpredictably.
  * *Single Paid Search Provider (e.g., Tavily Only):* [Certain] Rejected because it creates a mandatory API key dependency, preventing the system from running out-of-the-box in local development environments without credentials.
* **Accepted Operational Trade-off:** Requires maintaining multiple provider client adapters and mapping divergent external JSON response schemas into a single shared data model.

---

#### ADR-08: Relational Database Access Architecture

* **Status:** [Certain] Accepted & Binding.
* **Context:** The agent requires access to relational data without risking accidental data loss or destructive mutations caused by SQL injection or hallucinated commands.
* **Decision:** Deploy an embedded **SQLite database** using read-only URI connection strings (`file:...mode=ro`), exposing the table structure as an **MCP Resource** (`schema://main`) rather than a dynamic tool call.
* **Traceability:** Satisfies **US-01** (Data Retrieval) and **US-03** (Security Violation Guardrails).
* **Alternatives Evaluated & Rejected:**
  * *Unrestricted Read-Write SQL Tool:* [Certain] Rejected because prompt injection attacks can bypass system prompt guidelines to run destructive commands (`DROP TABLE`, `DELETE`), resulting in unrecoverable data loss.
  * *Containerized PostgreSQL with Network RBAC:* [Certain] Rejected because running an external database service adds container management, port mapping, and credential overhead without providing additional security over an SQLite database locked at the filesystem level.
* **Accepted Operational Trade-off:** SQLite does not support concurrent write transactions across multiple distributed threads, limiting this architecture to analytical read-only workflows rather than transactional application backends.

---

#### ADR-09: Telemetry & Cost Accounting Architecture

* **Status:** [Certain] Accepted & Binding.
* **Context:** System performance, token usage, and operational costs must be tracked without introducing third-party monitoring dependencies.
* **Decision:** Emit **un-nested, structured JSON telemetry** directly to standard output, incorporating a **shadow cloud cost calculation** that tracks physical token counts alongside simulated commercial API costs ($0.15/$0.60 per million tokens).
* **Traceability:** Satisfies **KPI 1.3** (100% Telemetry Coverage) and **Section 4.3** (Observability Schema).
* **Alternatives Evaluated & Rejected:**
  * *Unstructured Terminal `print()` Logging:* [Certain] Rejected because free-form text strings cannot be parsed or indexed by log management platforms (such as Datadog or Elasticsearch), making automated alerting and P95 latency tracking impossible.
  * *Proprietary SaaS APM Platforms (e.g., LangSmith):* [Certain] Rejected because third-party monitoring services create vendor lock-in, add outbound network calls to every execution, and prevent the system from running in fully offline, private environments.
* **Accepted Operational Trade-off:** Emitting structured JSON to standard output requires running a secondary log collector or parsing script to visualize traces in a dashboard, rather than providing an interactive web UI out of the box.

---

### ADR-10: Ollama Multi-Model Concurrency & Keep-Alive Policy

* **Status:** Accepted & Binding.
* **Decision:** Enforce Ollama multi-model residency by configuring `OLLAMA_MAX_LOADED_MODELS=2` and passing `keep_alive: -1` on local inference requests.
* **Traceability:** Satisfies KPI 1.3 (Execution Latency) and Section 6.1 (Compute Footprint).

#### ADR-11: MCP Stdio Client Bridge via `langchain-mcp-adapters`

* **Status:** Accepted & Binding.
* **Decision:** Standardize on `langchain-mcp-adapters` to bridge the FastMCP stdio JSON-RPC transport directly into LangGraph tool nodes.
* **Traceability:** Satisfies ADR-02, COMP-01, and COMP-04.

#### ADR-12: Resilient GPU Telemetry with Multi-Tier Fallback

* **Status:** Accepted & Binding.
* **Decision:** Replace `pynvml` with `nvidia-ml-py` and implement a 3-tier fallback hierarchy (Python API -> CLI `nvidia-smi` -> CI Mock).
* **Traceability:** Satisfies Task 0.1, COMP-08, and CI portability.

---

### 8. Architectural Traceability Cross-Reference

| Architectural Decision             | Direct PRD Requirement / KPI  | Primary Failure Mode Mitigated                                  |
| :--------------------------------- | :---------------------------- | :-------------------------------------------------------------- |
| **ADR-01: StateGraph**       | US-01, US-02, KPI 1.3         | Unrecoverable crashes during intermediate tool failures         |
| **ADR-02: FastMCP**          | Scope V1, FDE Standards       | Cascading agent host crashes caused by tool memory leaks        |
| **ADR-03: Docker Sandbox**   | US-03, KPI 1.3 (Security)     | Arbitrary host filesystem deletion and local network scanning   |
| **ADR-04: Qwen 2.5 7B Q4**   | KPI 1.3 (Latency$\le 8.5$s) | CUDA Out-of-Memory crashes and PCIe memory bus offloading       |
| **ADR-05: nomic-embed (8k)** | Section 6.1 (Context Budget)  | Silent truncation of complex multi-table database schemas       |
| **ADR-06: SHA-256 Hashing**  | US-02, KPI 1.3 (Loop Defense) | Runaway API spending caused by repetitive tool failures         |
| **ADR-07: Search Cascade**   | Section 6.3 (SSOF Avoidance)  | Automated CI test failures caused by anti-bot IP blocking       |
| **ADR-08: SQLite URI Mode**  | US-03 (SQL Guardrails)        | Accidental data loss caused by prompt injection attacks         |
| **ADR-09: Structured JSON**  | KPI 1.3 (Telemetry Coverage)  | Blind production debugging caused by unstructured terminal logs |

---

# Project: Enterprise MCP Tool-Calling Agent with Observability (Path 2)

**Document Version:** 1.1.0 (Post-Phase 1 Architecture Harmonization)
**Target Milestone:** MVP Release (V1)
**Status:** Phase 1 Complete / Phase 2 Active Implementation

---

## 1. Problem Statement & Success Metrics

### 1.1 Problem Statement

[Certain] Current autonomous ReAct implementations rely on loose, unbounded `while` loops that fail unpredictably in production: they enter cyclic tool-calling loops when tools fail, execute untrusted Python code directly on host runtimes, lack structured audit trails, and fail to manage token costs. This system delivers a deterministic, state-machine-backed agent utilizing the Model Context Protocol (MCP) to isolate tool execution, halt repetitive failure loops, and emit machine-readable telemetry for every state transition.

### 1.2 Target Audience

* **Forward Deployed Engineers (FDEs) & AI Platform Teams:** Requiring a verifiable, observable reference architecture for multi-tool orchestration.
* **Enterprise Data Analysts:** Needing automated, multi-step data retrieval (SQL), synthesis (Python), and external validation (Web Search) without security exposure.

### 1.3 Success Metrics (V1 Key Performance Indicators)

* **Loop Mitigation Rate:** [Certain] 100% of repetitive, identical tool invocations intercepted and halted at strike 3 via SHA-256 argument fingerprinting and SQL AST canonicalization.
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
  * **When:** The agent requests a tool call whose canonical argument hash matches 2 preceding calls in the same session (including SQL queries with shifted whitespace or case).
  * **Then:** The system intercepts execution, bypasses the tool, injects a `Circuit Breaker Triggered` message into context, and forces an alternate reasoning path.

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

| IN SCOPE (V1 MVP)                                        | OUT OF SCOPE (Future Releases)             |
| :------------------------------------------------------- | :----------------------------------------- |
| FastMCP Server via stdio JSON-RPC transport              | FastMCP over SSE / HTTP / Unix Sockets     |
| LangGraph StateGraph deterministic engine (v1.2.x)       | Web UI / Interactive Chat Frontend         |
| Tools:`web_search`, `run_python`, `query_database` | Human-in-the-Loop (HITL) pause nodes       |
| Schema Resource:`schema://main`                        | Database write permissions                 |
| SHA-256 + SQL AST Loop Detection (`sqlglot`)           | Dynamic vector-based tool routing          |
| Hardened Docker daemon container sandbox                 | Distributed multi-agent swarms             |
| Telemetry JSON Lines emitted to`sys.stderr`            | Distributed OpenTelemetry trace collectors |

---

## 4. Architectural Resolutions & Concrete Specifications

### 4.1 Model Runtime & Compute Budget Resolution

* **Selected Hardware Profile:** NVIDIA GeForce RTX 4060 Laptop GPU (8,192 MB GDDR6 physical VRAM).
* **Primary Local LLM:** `qwen2.5:7b-instruct-q4_K_M` served via Ollama (Static weights: ~4,400 MB; KV cache: ~1,200 MB).
* **CI Cloud Fallback:** OpenAI `gpt-4o-mini` activated automatically when Ollama is unreachable.
* **Concurrency & Keep-Alive:** Enforced `OLLAMA_MAX_LOADED_MODELS=2` and `keep_alive: -1` to avoid PCIe bus reloading latency.

### 4.2 Code Execution Isolation & Sandbox Resolution

* **Isolation Engine:** Docker Engine API socket (`/var/run/docker.sock`).
* **Container Parameters:** `python:3.11-slim`, `--network none`, `--memory 256m`, `--cpus 1.0`, `--read-only`, tmpfs at `/tmp:rw,size=16m`, executed as user `nobody`.
* **Execution Timeout:** Hard 5.0-second wall-clock termination managed via container lifecycle polling and `container.kill()`.
* **Observed Metrics:** Benchmark confirmed P50 execution latency of 1,034.09 ms for analytical tasks.

### 4.3 Database Access Architecture

* **Physical File:** Embedded SQLite (`company_metrics.db`).
* **Connection Security:** URI connection with `mode=ro`.
* **Engine Interception:** C-level `sqlite3.Connection.set_authorizer` callback rejecting all actions outside `SQLITE_SELECT`, `SQLITE_READ`, and `SQLITE_FUNCTION`.

---

## 5. Architectural Decision Records (ADRs)

*(ADR-01 through ADR-12 retained as ratified)*

### ADR-0013: Stream Demultiplexing for FastMCP and Observability

* **Status:** Accepted & Binding.
* **Context:** FastMCP over stdio requires exclusive ownership of `sys.stdout` for newline-delimited JSON-RPC 2.0 frames. Writing JSON telemetry to `stdout` breaks client JSON-RPC parsers.
* **Decision:** Reserve `sys.stdout` exclusively for FastMCP protocol transport. Designate `sys.stderr` as the transport for all un-nested JSON telemetry events, system alerts, and debug logs.
* **Traceability:** Satisfies Section 1.3 (Telemetry Coverage) and Section 3 (FastMCP stdio).

### ADR-0014: SQLite C-Level Authorizer Engine Integration

* **Status:** Accepted & Binding.
* **Context:** Regex token filters are porous and easily bypassed by SQL comments, casing tricks, or subqueries.
* **Decision:** Implement engine-level security using `sqlite3.Connection.set_authorizer`. Deny all structural mutations (`SQLITE_DENY`) while permitting read operations (`SQLITE_OK`).
* **Traceability:** Satisfies US-03 and KPI 1.3 (Containment).

### ADR-0015: Runtime Dependency Harmonization (LTS 2026 Baseline)

* **Status:** Accepted & Binding.
* **Context:** `langchain-mcp-adapters>=0.3.0` and `fastmcp>=4.0.0` require `langchain-core>=1.0.0`, conflicting with legacy 0.x bounds.
* **Decision:** Upgrade the runtime stack to modern LTS baselines: `langchain-core>=1.0.0`, `langgraph>=1.0.0`, `fastmcp>=4.0.0`, `mcp>=2.0.0`, and `sqlglot>=30.0.0`. Inspect distribution metadata via `importlib.metadata`.
* **Traceability:** Resolves build packaging conflicts and guarantees long-term stability.
