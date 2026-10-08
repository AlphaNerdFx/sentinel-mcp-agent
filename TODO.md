# TODO.md: Enterprise MCP Tool-Calling Agent (V1 Release Roadmap)

**Target Milestone:** Version 1.0.0 (Production Framework Stack)
**Tracking PRD:** `PRD_V1.md`
**Standard:** Forward Deployed Engineer (FDE) Portfolio Grade

---

## Phase 0: Hardware Baseline & Environment Gate (Prerequisites)

*Objective: Prove that local hardware, container runtimes, and local model engines are operational before writing application code.*

- [x] **Task 0.1: Verify CUDA & VRAM Budget Allocation**
  - [x] Standalone verification script (`scripts/check_env.py`) implemented with `nvidia-ml-py` and CLI fallback (ADR-12).
  - [x] *Acceptance Criteria Met:* Verified 1,842 MB free VRAM with model warm-loaded (>= 1,000 MB unallocated headroom constraint satisfied) [Certain].
- [x] **Task 0.2: Local Model & Embedder Provisioning**
  - [x] Provisioned `qwen2.5:7b-instruct-q4_K_M` and `nomic-embed-text:v1.5` on local Ollama service.
  - [x] Validated dual-model concurrency configuration and warm single-token ping < 2.0s via `keep_alive: -1` (ADR-10).
  - [x] *Acceptance Criteria Met:* Combined weights loaded in VRAM within allocation boundaries [Certain].
- [x] **Task 0.3: Docker Daemon Socket Permission Verification**
  - [x] Implemented Python SDK socket verification script (`scripts/test_docker_socket.py`).
  - [x] Verified non-root access to `/var/run/docker.sock` and enforced COMP-05 constraints (`network_mode="none"`, `mem_limit="256m"`, `tmpfs`).
  - [x] *Acceptance Criteria Met:* Verified deterministic Linux OOM-killer termination with exit code 137 [Certain].
- [x] **Task 0.4: Dependency Manifest & Virtual Environment**
  - [x] Created Python 3.11 isolated virtual environment.
  - [x] Configured PEP 621 `pyproject.toml` and compiled deterministic `requirements.lock` via `pip-tools`.
  - [x] Added `langchain-mcp-adapters` for stdio JSON-RPC client integration (ADR-11).

---

## Phase 1: Tool Engine & Isolation Primitives

*Objective: Implement and unit-test all MCP tools, resources, and sandboxes in complete isolation from the agent.*

- [ ] **Task 1.1: Containerized Code Execution Sandbox (`src/sandbox/docker_runner.py`)**
  - [ ] Implement `DockerPythonSandbox` class wrapping the Docker Engine API.
  - [ ] Enforce security constraints: `--network none`, `--memory 256m`, `--cpus 1.0`, `--read-only`, and `--tmpfs /tmp:rw,size=16m`.
  - [ ] Implement 5-second wall-clock termination using container polling and force-kill (`container.kill()`).
  - [ ] *Acceptance Criteria:* Unit test confirms that attempting an outbound HTTP request inside the sandbox fails immediately with a network error [Certain].
- [ ] **Task 1.2: Relational Database & Read-Only SQLite Engine (`src/tools/database.py`)**
  - [ ] Implement database initialization script seeding `company_metrics.db` with sample revenue records.
  - [ ] Implement query function using SQLite URI read-only mode (`file:company_metrics.db?mode=ro`).
  - [ ] Implement SQL validation gate: reject queries containing `DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, or `TRUNCATE`.
  - [ ] *Acceptance Criteria:* Executing `DROP TABLE product_revenue` returns a `Security Violation` error string without touching the database file [Certain].
- [ ] **Task 1.3: Resilient Multi-Provider Search Engine (`src/tools/search.py`)**
  - [ ] Define Pydantic models: `SearchResultItem` and `UnifiedSearchResponse`.
  - [ ] Implement `ResilientSearchEngine` with Chain of Responsibility cascade:
    1. Primary: DuckDuckGo (zero-key).
    2. Secondary: Tavily Search (reads `TAVILY_API_KEY`).
    3. Tertiary: Brave Search (reads `BRAVE_API_KEY`).
  - [ ] Handle exhaustion gracefully: return empty list with `provider_used="Exhausted"` instead of raising unhandled exceptions.
  - [ ] *Acceptance Criteria:* Simulating a rate-limit error (HTTP 429) on DuckDuckGo automatically cascades execution to Tavily and returns normalized results [Certain].
- [ ] **Task 1.4: FastMCP Tool Server Packaging (`src/server.py`)**
  - [ ] Register `web_search`, `query_database`, and `run_python` using `@mcp.tool()` decorators.
  - [ ] Register table schema as an MCP Resource using `@mcp.resource("schema://main")`.
  - [ ] Configure server entry point to serve over standard I/O (`transport="stdio"`).
  - [ ] *Acceptance Criteria:* Running `python src/server.py` waits for standard input and responds correctly to JSON-RPC initialization pings [Certain].

---

## Phase 2: State Machine Orchestration & Safety Guardrails

*Objective: Build the deterministic LangGraph engine, loop detection circuit breaker, and model provider adapters.*

- [ ] **Task 2.1: Model Provider Adapter (`src/agent/model_adapter.py`)**
  - [ ] Implement `get_model()` factory returning a configured `ChatOpenAI` client.
  - [ ] Configure local path: point `base_url` to `http://localhost:11434/v1` with model `qwen2.5:7b-instruct`.
  - [ ] Configure CI fallback path: check for `OPENAI_API_KEY`; if present and Ollama is unreachable, point to cloud API.
  - [ ] Bind MCP tool schemas to the model instance.
- [ ] **Task 2.2: State Schema & Deduplication Engine (`src/agent/state.py`)**
  - [ ] Define `AgentState` typed dictionary containing `messages`, `iteration_count`, `tool_call_history`, and `session_id`.
  - [ ] Implement canonical SHA-256 fingerprinting function:
    $$
    \text{Hash} = \text{SHA256}(\text{tool\_name} + \text{":""} + \text{canonical\_json}(\text{args}))
    $$
  - [ ] *Acceptance Criteria:* Verify that `{"a": 1, "b": 2}` and `{"b": 2, "a": 1}` generate identical hashes [Certain].
- [ ] **Task 2.3: LangGraph Node Implementation (`src/agent/nodes.py`)**
  - [ ] Implement `agent_node`: invokes LLM, captures latency, extracts token metrics, and increments iteration counter.
  - [ ] Implement `tool_node`: iterates through requested tool calls, hashes signatures, tracks repetition counts, and routes calls to execution.
  - [ ] Implement `circuit_breaker` logic inside `tool_node`: if an identical hash occurs 3 times, intercept the call, bypass tool execution, and inject a warning `ToolMessage`.
  - [ ] Implement `force_end_node`: generates a structured fallback message when iteration count reaches 10.
- [ ] **Task 2.4: StateGraph Assembly & Compilation (`src/agent/graph.py`)**
  - [ ] Initialize `StateGraph(AgentState)`.
  - [ ] Add nodes: `agent`, `tools`, `force_end`.
  - [ ] Configure conditional edges via `should_continue` router:
    - Route to `force_end` if `iteration_count >= 10`.
    - Route to `tools` if model emits tool calls.
    - Route to `END` if model emits final response without tool calls.
  - [ ] Compile graph into executable runnable (`app = workflow.compile()`).

---

## Phase 3: Structured Telemetry & Observability Layer

*Objective: Implement machine-readable JSON logging to stdout with dual-metric cost accounting.*

- [ ] **Task 3.1: Structured Telemetry Logger (`src/telemetry/logger.py`)**
  - [ ] Implement `StructuredLogger.log_event(event_type, node, metrics, payload)`.
  - [ ] Enforce schema matching PRD Section 4.3 (RFC 3339 timestamps, UUID session IDs, un-nested JSON lines).
  - [ ] Output strictly to `sys.stdout`.
- [ ] **Task 3.2: Dual-Metric Cost Calculation Engine (`src/telemetry/cost.py`)**
  - [ ] Define model pricing table ($0.15 / 1M prompt tokens, $0.60 / 1M completion tokens).
  - [ ] Implement shadow cost calculator converting input/output tokens into simulated USD spend.
  - [ ] Track actual hardware execution metrics: latency in milliseconds and tokens-per-second generation rate.
  - [ ] *Acceptance Criteria:* Every LLM completion event prints a valid JSON line containing both token counts and estimated dollar costs [Certain].

---

## Phase 4: Verification Suite & CI/CD Pipeline

*Objective: Build automated tests proving all PRD acceptance criteria and security bounds are met.*

- [ ] **Task 4.1: Unit Test Suite (`tests/unit/`)**
  - [ ] `test_sandbox_security.py`: Verifies network block, 5s timeout kill, and 256MB RAM exhaustion handling (`ExitCode 137`).
  - [ ] `test_sql_guardrails.py`: Verifies that destructive queries (`DROP`, `DELETE`, `UPDATE`) are rejected without database modification.
  - [ ] `test_search_fallback.py`: Mocks DuckDuckGo failure and verifies automatic fallback to Tavily.
  - [ ] `test_loop_detector.py`: Verifies that SHA-256 argument fingerprinting catches duplicate calls regardless of dictionary key ordering.
- [ ] **Task 4.2: End-to-End User Story Tests (`tests/e2e/`)**
  - [ ] `test_us01_multistep_query.py`: Verifies that the agent queries SQL for revenue data, passes it to Python to compute a 15% increase, and returns the final answer in $\le 4$ steps.
  - [ ] `test_us02_loop_interception.py`: Injects a failing tool scenario and verifies the circuit breaker halts execution at strike 3 without reaching the 10-step cap.
  - [ ] `test_us03_security_containment.py`: Prompts the agent to run dangerous code (e.g., file deletion) and verifies the attempt is blocked.
- [ ] **Task 4.3: GitHub Actions CI Workflow (`.github/workflows/ci.yml`)**
  - [ ] Configure Ubuntu runner with Docker service enabled.
  - [ ] Add steps: checkout code, setup Python 3.11, install dependencies.
  - [ ] Execute unit tests and mock integration tests.
  - [ ] *Acceptance Criteria:* Pull requests trigger automated test runs and must pass all unit tests before merging [Certain].

---

## Phase 5: Production Packaging & Portfolio Documentation

*Objective: Finalize the repository for review by hiring managers and engineering leads.*

- [ ] **Task 5.1: Zero-Config CLI Entry Point (`main.py`)**
  - [ ] Build interactive CLI interface accepting user prompts via terminal arguments or interactive input.
  - [ ] Add `--verbose` flag to toggle display of real-time structured telemetry logs.
- [ ] **Task 5.2: Production Documentation (`README.md`)**
  - [ ] Document project architecture, design trade-offs, and setup steps.
  - [ ] Include ASCII architecture diagrams illustrating data flow.
  - [ ] Document VRAM sizing calculations and Docker socket setup for Ubuntu, macOS, and Windows/WSL2.
- [ ] **Task 5.3: Verification of KPIs Against Acceptance Criteria**
  - [ ] Measure P95 multi-tool execution latency; verify $\le 8.5\text{ seconds}$ on standard local runs [Likely].
  - [ ] Verify 100% loop break rate across test suites.
  - [ ] Verify 0 unauthorized host OS operations across all tests.
