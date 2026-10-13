# TODO.md: Enterprise MCP Tool-Calling Agent (V1 Release Roadmap)

**Target Milestone:** Version 1.0.0 (Production Framework Stack)
**Tracking PRD:** `PRD_V1.md`
**Standard:** Forward Deployed Engineer (FDE) Portfolio Grade

---

## Phase 0: Hardware Baseline & Environment Gate (Prerequisites)

*Objective: Prove that local hardware, container runtimes, and local model engines are operational before writing application code.*

- [X] **Task 0.1: Verify CUDA & VRAM Budget Allocation**
  - [X] Standalone verification script (`scripts/check_env.py`) implemented with `nvidia-ml-py` and CLI fallback (ADR-12).
  - [X] *Acceptance Criteria Met:* Verified 1,842 MB free VRAM with model warm-loaded (>= 1,000 MB unallocated headroom constraint satisfied) [Certain].
- [X] **Task 0.2: Local Model & Embedder Provisioning**
  - [X] Provisioned `qwen2.5:7b-instruct-q4_K_M` and `nomic-embed-text:v1.5` on local Ollama service.
  - [X] Validated dual-model concurrency configuration and warm single-token ping < 2.0s via `keep_alive: -1` (ADR-10).
  - [X] *Acceptance Criteria Met:* Combined weights loaded in VRAM within allocation boundaries [Certain].
- [X] **Task 0.3: Docker Daemon Socket Permission Verification**
  - [X] Implemented Python SDK socket verification script (`scripts/test_docker_socket.py`).
  - [X] Verified non-root access to `/var/run/docker.sock` and enforced COMP-05 constraints (`network_mode="none"`, `mem_limit="256m"`, `tmpfs`).
  - [X] *Acceptance Criteria Met:* Verified deterministic Linux OOM-killer termination with exit code 137 [Certain].
- [X] **Task 0.4: Dependency Manifest & Virtual Environment**
  - [X] Created Python 3.11 isolated virtual environment.
  - [X] Configured PEP 621 `pyproject.toml` and compiled deterministic `requirements.lock` via `pip-tools`.
  - [X] Replaced legacy `langchain-mcp-adapters` with native FastMCP 4.x stdio client integration due to upstream MCP 2.x breaking changes (ADR-0019 supersedes ADR-11) [Certain].

---

## Phase 1: Tool Engine & Isolation Primitives

*Objective: Implement and unit-test all MCP tools, resources, and sandboxes in complete isolation from the agent.*

- [X] **Task 1.1: Containerized Code Execution Sandbox (`src/sandbox/docker_runner.py`)**
  - [X] Implement `DockerPythonSandbox` class wrapping the Docker Engine API.
  - [X] Enforce security constraints: `--network none`, `--memory 256m`, `--cpus 1.0`, `--read-only`, and `--tmpfs /tmp:rw,size=16m`.
  - [X] Implement 5-second wall-clock termination using container polling and force-kill (`container.kill()`).
  - [X] *Acceptance Criteria Met:* Unit test confirms that attempting an outbound HTTP request inside the sandbox fails immediately with a network error [Certain].
- [X] **Task 1.2: Relational Database & Read-Only SQLite Engine (`src/tools/database.py`)**
  - [X] Implement database initialization script seeding `company_metrics.db` with sample revenue records.
  - [X] Implement query function using SQLite URI read-only mode (`file:company_metrics.db?mode=ro`).
  - [X] Implement C-level SQLite engine authorizer callback (ADR-0014) blocking write actions at the database engine level.
  - [X] *Acceptance Criteria Met:* Executing `DROP TABLE product_revenue` returns an authorization denial error string without touching the database file [Certain].
- [X] **Task 1.3: Resilient Multi-Provider Search Engine (`src/tools/search.py`)**
  - [X] Define Pydantic models: `SearchResultItem` and `UnifiedSearchResponse`.
  - [X] Implement `ResilientSearchEngine` with Chain of Responsibility cascade:
    1. Primary: DuckDuckGo (zero-key).
    2. Secondary: Tavily Search (reads `TAVILY_API_KEY`).
    3. Tertiary: Brave Search (reads `BRAVE_API_KEY`).
  - [X] Handle exhaustion gracefully: return empty list with `provider_used="Exhausted"` instead of raising unhandled exceptions.
  - [X] *Acceptance Criteria Met:* Simulating a rate-limit error (HTTP 429) on DuckDuckGo automatically cascades execution to Tavily and returns normalized results [Certain].
- [X] **Task 1.4: FastMCP Tool Server Packaging (`src/server.py`)**
  - [X] Register `web_search`, `query_database`, and `run_python` using `@mcp.tool()` decorators.
  - [X] Register table schema as an MCP Resource using `@mcp.resource("schema://main")`.
  - [X] Configure server entry point to serve over standard I/O (`transport="stdio"`).
  - [X] Ensure all diagnostics and server logs route exclusively to `sys.stderr` (ADR-0013).
  - [X] *Acceptance Criteria Met:* Running `python src/server.py` waits for standard input and responds correctly to JSON-RPC initialization pings [Certain].

---

## Phase 2: State Machine Orchestration & Safety Guardrails

*Objective: Build the deterministic LangGraph engine, loop detection circuit breaker, and model provider adapters.*

- [X] **Task 2.1: Model Provider Adapter (`src/agent/model_adapter.py`)**
  - [X] Implement `get_model()` factory returning a configured `ChatOpenAI` client.
  - [X] Configure local path: point `base_url` to `http://localhost:11434/v1` with pinned model `qwen2.5:7b-instruct-q4_K_M` and configurable transport deadline (`MODEL_TIMEOUT=120.0`) (ADR-10).
  - [X] Configure CI fallback path: check for `OPENAI_API_KEY`; if present and Ollama is unreachable, point to `gpt-4o-mini`.
  - [X] Implement native FastMCP Client Manager (`src/agent/mcp_client.py`) using `fastmcp.Client` with dynamic Pydantic schema synthesis and `StructuredTool` adaptation (ADR-0019) [Certain].
- [X] **Task 2.2: State Schema & Deduplication Engine (`src/agent/state.py`)**
  - [X] Define `AgentState` typed dictionary containing `messages`, `iteration_count`, `tool_call_history`, and `session_id`.
  - [X] Implement domain-aware canonical SHA-256 fingerprinting function:
    $$
    \text{Hash} = \text{SHA256}(\text{tool\_name} + \text{":""} + \text{canonical\_payload}(\text{args}))
    $$
  - [X] Integrate `sqlglot` AST transpilation into `canonical_payload` with commutative binary equality sorting (`_canonicalize_ast`) (ADR-0015) [Certain].
  - [X] *Acceptance Criteria Met:* Verified that `{"a": 1, "b": 2}` and `{"b": 2, "a": 1}` match, and `SELECT * FROM t WHERE a = 1` and `select * from t where 1 = a` match via commutative AST parsing [Certain].
- [X] **Task 2.3: LangGraph Node Implementation (`src/agent/nodes.py`)**
  - [X] Implement `agent_node`: invokes LLM via non-streaming `ainvoke`, captures latency, extracts token metrics, and emits structured telemetry to `sys.stderr` [Certain].
  - [X] Implement atomic `tool_node`: partitions parallel calls into safe vs tripped, injects synthetic `ToolMessage` instances for calls with >= 3 strikes, executes safe calls via MCP client, and guarantees 100% `tool_call_id` wire compliance (ADR-0017) [Certain].
  - [X] Implement `force_end_node`: reconciles dangling tool calls asynchronously before emitting terminal `AIMessage` upon reaching 10 iterations [Certain].
- [X] **Task 2.4: StateGraph Assembly & Compilation (`src/agent/graph.py`)**
  - [X] Initialize `StateGraph(AgentState)` with pure asynchronous closures (`run_agent`, `run_tools`, `run_force_end`) preserving Python `CO_COROUTINE` code object flags [Certain].
  - [X] Add nodes: `agent`, `tools`, `force_end` [Certain].
  - [X] Configure conditional edge router from `agent`:
    - Route to `force_end` if `iteration_count >= 10`.
    - Route to `tools` if model emits tool calls.
    - Route to `END` if model emits response without tool calls.
  - [X] Connect `tools` back to `agent`, and `force_end` to `END` [Certain].
  - [X] Compile graph into executable runnable using `AsyncSqliteSaver` in WAL mode (`.agent_state.db`) (ADR-0016) [Certain].
  - [X] *Acceptance Criteria Met:* Live trajectory verified via `scripts/verify_phase2_live.py` against local Ollama instance and out-of-process FastMCP server [Certain].

---

## Phase 3: Structured Telemetry & Observability Layer

*Objective: Verify machine-readable JSON logging to stderr with dual-metric cost accounting.*

- [X] **Task 3.1: Structured Telemetry Logger (`src/telemetry/logger.py`)**
  - [X] Implement `StructuredLogger.log_event(event_type, node, metrics, payload)`.
  - [X] Enforce schema matching PRD Section 4.3 (RFC 3339 timestamps, UUID session IDs, flat JSON lines).
  - [X] Output strictly to `sys.stderr` to prevent stdio stream collisions (ADR-0013) [Certain].
- [X] **Task 3.2: Dual-Metric Cost Calculation Engine (`src/telemetry/cost.py`)**
  - [X] Define model pricing table ($0.15 / 1M prompt tokens, $0.60 / 1M completion tokens).
  - [X] Implement shadow cost calculator converting input/output tokens into simulated USD spend.
  - [X] Track actual hardware execution metrics: latency in milliseconds and tokens-per-second generation rate.
  - [X] *Acceptance Criteria Met:* Every LLM completion event emits a valid JSON line containing both token counts and estimated dollar costs [Certain].

---

## Phase 4: Verification Suite & CI/CD Pipeline

*Objective: Build automated tests proving all PRD acceptance criteria and security bounds are met.*

- [ ] **Task 4.1: Unit Test Suite (`tests/unit/`)**
  - [ ] `test_sandbox_security.py`: Verifies network block, 5s timeout kill, and 256MB RAM exhaustion handling (`ExitCode 137`).
  - [ ] `test_sql_guardrails.py`: Verifies that destructive queries (`DROP`, `DELETE`, `UPDATE`) are rejected without database modification via C-authorizer (ADR-0014).
  - [ ] `test_search_fallback.py`: Mocks DuckDuckGo failure and verifies automatic fallback to Tavily.
  - [ ] `test_loop_detector.py`: Verifies that commutative AST fingerprinting catches duplicate calls regardless of key ordering, casing, or binary operator operand inversion (`1 = id` vs `id = 1`) (ADR-0015).
  - [ ] `test_telemetry_schema.py`: Verifies that logs emit to `sys.stderr` and conform to the PRD Section 4.3 JSON schema.
- [ ] **Task 4.2: End-to-End User Story Tests (`tests/e2e/`)**
  - [ ] `test_us01_multistep_query.py`: Verifies that the agent queries SQL for revenue data, passes it to Python to compute a 15% increase, and returns the final answer in $\le 4$ steps.
  - [ ] `test_us02_loop_interception.py`: Injects a failing tool scenario and verifies the circuit breaker halts execution at strike 3 without reaching the 10-step cap or dropping `tool_call_id`s (ADR-0017).
  - [ ] `test_us03_security_containment.py`: Prompts the agent to run dangerous code (e.g., file deletion) and verifies the attempt is blocked.
- [ ] **Task 4.3: GitHub Actions CI Workflow (`.github/workflows/ci.yml`)**
  - [ ] Configure Ubuntu runner with Docker service enabled.
  - [ ] Add steps: checkout code, setup Python 3.11, install dependencies strictly from `requirements.lock` via `pip-sync`.
  - [ ] Configure test execution: run hermetic unit tests with mocked Ollama/cloud providers; run e2e tests gated by environment secrets.
  - [ ] *Acceptance Criteria:* Pull requests trigger automated test runs and must pass all unit tests before merging [Certain].

---

## Phase 5: Production Packaging & Portfolio Documentation

*Objective: Finalize the repository for review by hiring managers and engineering leads.*

- [ ] **Task 5.1: Zero-Config CLI Entry Point (`main.py`)**
  - [ ] Build interactive CLI interface accepting user prompts via terminal arguments or interactive REPL (`--interactive`).
  - [ ] Add `--verbose` flag to toggle display of real-time structured telemetry logs from `sys.stderr`.
  - [ ] Support `--session-id` argument to resume persistent conversations via SQLite WAL checkpointer (ADR-0016).
- [ ] **Task 5.2: Production Documentation (`README.md`)**
  - [ ] Document project architecture, design trade-offs, and setup steps.
  - [ ] Include ASCII architecture diagrams illustrating data flow and ADR-0013 stream demultiplexing.
  - [ ] Document VRAM sizing calculations and Docker socket setup for Ubuntu, macOS, and Windows/WSL2.
- [ ] **Task 5.3: Verification of KPIs Against Acceptance Criteria**
  - [ ] Measure P95 multi-tool execution latency; verify $\le 8.5\text{ seconds}$ on standard warm local runs [Likely].
  - [ ] Verify 100% loop break rate across test suites.
  - [ ] Verify 0 unauthorized host OS operations across all tests.