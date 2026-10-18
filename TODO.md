# TODO.md: Sentinel MCP Agent (V1 Release Roadmap)

**Target Milestone:** Version 1.0.0 (Production Reference Stack)
**Tracking PRD:** `PRD_V1.md` (v1.3.0)
**Standard:** Forward Deployed Engineer (FDE) Portfolio Grade
**Current Status:** Phase 4 Signed Off (v0.4.0-phase4) | Phase 5 Active

---

## Phase 0: Hardware Baseline & Environment Gate (Prerequisites)

- [X] **Task 0.1: Verify CUDA & VRAM Budget Allocation**
  - [X] Standalone verification script (`scripts/check_env.py`) implemented with `nvidia-ml-py` and CLI fallback (ADR-0012).
  - [X] *Acceptance Criteria Met:* Verified 1,842 MB free VRAM with model warm-loaded (>= 1,000 MB unallocated headroom constraint satisfied) [Certain].
- [X] **Task 0.2: Local Model & Embedder Provisioning**
  - [X] Provisioned `qwen2.5:7b-instruct-q4_K_M` and `nomic-embed-text:v1.5` on local Ollama service.
  - [X] Validated dual-model concurrency configuration and warm single-token ping < 2.0s via `keep_alive: -1` (ADR-0010).
  - [X] *Acceptance Criteria Met:* Combined weights loaded in VRAM within allocation boundaries [Certain].
- [X] **Task 0.3: Docker Daemon Socket Permission Verification**
  - [X] Implemented Python SDK socket verification script (`scripts/test_docker_socket.py`).
  - [X] Verified non-root access to `/var/run/docker.sock` and enforced COMP-05 constraints (`network_mode="none"`, `mem_limit="256m"`, `tmpfs`).
  - [X] *Acceptance Criteria Met:* Verified deterministic Linux OOM-killer termination with exit code 137 [Certain].
- [X] **Task 0.4: Dependency Manifest & Virtual Environment**
  - [X] Created Python 3.11 isolated virtual environment.
  - [X] Configured PEP 621 `pyproject.toml` and compiled deterministic `requirements.lock` via `pip-tools`.
  - [X] Replaced legacy `langchain-mcp-adapters` with native FastMCP 4.x stdio client integration due to upstream MCP 2.x breaking changes (ADR-0019 supersedes ADR-0011) [Certain].

---

## Phase 1: Tool Engine & Isolation Primitives

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
  - [X] Handle exhaustion gracefully: return empty list with `provider_used="Exhausted"` instead of raising unhandled exceptions (ADR-0007).
  - [X] *Acceptance Criteria Met:* Simulating a rate-limit error (HTTP 429) on DuckDuckGo automatically cascades execution to Tavily and returns normalized results [Certain].
- [X] **Task 1.4: FastMCP Tool Server Packaging (`src/server.py`)**
  - [X] Register `web_search`, `query_database`, and `run_python` using `@mcp.tool()` decorators.
  - [X] Register table schema as an MCP Resource using `@mcp.resource("schema://main")`.
  - [X] Configure server entry point to serve over standard I/O (`transport="stdio"`).
  - [X] Ensure all diagnostics and server logs route exclusively to `sys.stderr` (ADR-0013).
  - [X] *Acceptance Criteria Met:* Running `python src/server.py` waits for standard input and responds correctly to JSON-RPC initialization pings [Certain].

---

## Phase 2: State Machine Orchestration & Safety Guardrails

- [X] **Task 2.1: Model Provider Adapter (`src/agent/model_adapter.py`)**
  - [X] Implement `get_model()` factory returning a configured `ChatOpenAI` client.
  - [X] Configure local path: point `base_url` to `http://localhost:11434/v1` with pinned model `qwen2.5:7b-instruct-q4_K_M` and transport deadline (`MODEL_TIMEOUT=120.0`) (ADR-0010).
  - [X] Configure CI fallback path: check for `OPENAI_API_KEY`; if present and Ollama is unreachable, point to `gpt-4o-mini`.
  - [X] Implement native FastMCP Client Manager (`src/agent/mcp_client.py`) using `fastmcp.Client` with dynamic Pydantic schema synthesis and `StructuredTool` adaptation (ADR-0019) [Certain].
- [X] **Task 2.2: State Schema & Deduplication Engine (`src/agent/state.py`)**
  - [X] Define `AgentState` typed dictionary containing `messages`, `iteration_count`, `tool_call_history`, and `session_id`.
  - [X] Implement domain-aware canonical SHA-256 fingerprinting function using `sqlglot` AST traversal with commutative equality and boolean junction normalization (ADR-0016) [Certain].
- [X] **Task 2.3: LangGraph Node Implementation (`src/agent/nodes.py`)**
  - [X] Implement `agent_node`: invokes LLM via non-streaming `ainvoke`, captures latency, extracts token metrics, and emits structured telemetry to `sys.stderr` [Certain].
  - [X] Implement atomic `tool_node`: partitions parallel calls into safe vs tripped, injects synthetic `ToolMessage` instances for calls with >= 3 strikes, executes safe calls via MCP client, and guarantees 100% `tool_call_id` wire compliance (ADR-0018) [Certain].
  - [X] Implement `force_end_node`: reconciles dangling tool calls asynchronously before emitting terminal `AIMessage` upon reaching 10 iterations [Certain].
- [X] **Task 2.4: StateGraph Assembly & Compilation (`src/agent/graph.py`)**
  - [X] Initialize `StateGraph(AgentState)` with pure asynchronous closures preserving Python `CO_COROUTINE` flags [Certain].
  - [X] Configure conditional edge router `route_agent_output`: enforce iteration ceiling at 10 turns.
  - [X] Compile graph into executable runnable using `AsyncSqliteSaver` in WAL mode (`.agent_state.db`) (ADR-0017) [Certain].

---

## Phase 3: Structured Telemetry & Observability Layer

- [X] **Task 3.1: Structured Telemetry Logger (`src/telemetry/logger.py`)**
  - [X] Implement `StructuredLogger.log_event(event_type, node, metrics, payload)`.
  - [X] Enforce schema matching PRD Section 4.3 (RFC 3339 timestamps, UUID session IDs, flat JSON lines).
  - [X] Output strictly to `sys.stderr` to prevent stdio stream collisions (ADR-0013) [Certain].
- [X] **Task 3.2: Dual-Metric Cost Calculation Engine (`src/telemetry/cost.py`)**
  - [X] Define model pricing table ($0.15 / 1M prompt tokens, $0.60 / 1M completion tokens).
  - [X] Implement shadow cost calculator converting input/output tokens into simulated USD spend.
  - [X] Track actual hardware execution metrics: latency in milliseconds and tokens-per-second generation rate [Certain].

---

## Phase 4: Verification Suite & CI/CD Pipeline

- [X] **Task 4.1: Unit Test Suite (`tests/unit/`)**

  - [X] `tests/unit/tools/test_sandbox_security.py`: Verifies network block, 5s timeout kill, 256MB RAM OOM termination (`ExitCode 137`), and kernel VFS write refusal (`EROFS`/`EACCES`).
  - [X] `tests/unit/tools/test_sql_guardrails.py`: Verifies C-authorizer rejects DDL (`DROP`), DML (`DELETE`, `UPDATE`), system PRAGMAs, and database smuggling (`ATTACH`) at the engine layer (ADR-0014).
  - [X] `tests/unit/tools/test_search_fallback.py`: Verifies 3-tier cascade logic and unconfigured key bypassing without external network calls (ADR-0007).
  - [X] `tests/unit/tools/test_mcp_server.py`: Verifies FastMCP primitives over stdio and resource registration.
  - [X] `tests/unit/agent/test_model_adapter.py`: Verifies Ollama probe detection, gpt-4o-mini cloud fallback, and 120s timeout parsing.
  - [X] `tests/unit/agent/test_state_graph.py`: Verifies 3-node topology, iteration ceiling cutoff at 10 turns, and dangling tool call reconciliation.
  - [X] `tests/unit/agent/test_loop_detector.py`: Verifies commutative AST equality, relational inversion, boolean `AND`/`OR` sorting, and JSON key ordering (ADR-0016).
  - [X] `tests/unit/agent/test_telemetry_schema.py`: Verifies JSON lines emission strictly to `sys.stderr` with guaranteed `session_id` propagation.
  - [X] *Acceptance Criteria Met:* All 54 unit tests pass in 9.27 seconds on GitHub Actions hosted runners [Certain].
- [X] **Task 4.2: End-to-End User Story Tests (`tests/e2e/`)**

  - [X] `test_us01_multistep_query.py`: Verifies multi-step analytical execution (SQL $\rightarrow$ Python 15% projection $\rightarrow$ Synthesis in $\le 4$ steps).
  - [X] `test_us02_loop_interception.py`: Verifies repetitive tool invocations halt at Strike 3 with synthetic `ToolMessage` without wire protocol drops (ADR-0018).
  - [X] `test_us03_security_containment.py`: Verifies that destructive SQL (`DROP TABLE`) and socket scans (`port 53`) are intercepted through the LangGraph state machine.
  - [X] *Acceptance Criteria Met:* All 4 E2E user story integration tests pass hermetically [Certain].
- [X] **Task 4.3: CI/CD Pipeline Automation & Toolchain Hardening**

  - [X] Configure `.github/workflows/ci.yml` running on Ubuntu runners with pre-installed Docker services.
  - [X] Lock dependencies via `requirements.lock` including development extras (`--extra=dev`).
  - [X] Configure automation `Makefile` with whitespace-immune relative paths and `.gitattributes` LF line-ending normalization.
  - [X] Enforce strict static type checking via Mypy (17/17 source files passing with 0 errors).
  - [X] Enforce style formatting and linting via Ruff (28/28 files clean).
  - [X] Implement automated FastMCP stdio stream purity verification (zero bytes on `stdout`).
  - [X] Implement SQLite database self-seeding (`company_metrics.db`) to guarantee hermetic execution on clean checkouts.
  - [X] *Acceptance Criteria Met:* Remote GitHub Actions workflow executes `make ci` and turns 100% green on push [Certain].

---

## Phase 5: Production Packaging & Portfolio Documentation (ACTIVE)

- [X] **Task 5.1: Zero-Config CLI Entry Point (`main.py`)**
  - [X] Implement command-line interface supporting positional prompt arguments: `python main.py "Calculate Q3 revenue"`.
  - [X] Support interactive multi-turn REPL mode via `--interactive` flag.
  - [X] Support persistent conversational session resumption via `--session-id <UUID>` targeting `.agent_state.db` (ADR-0017).
  - [X] Support `--verbose` flag toggling display of real-time structured telemetry events from `sys.stderr`.
  - [X] Implement deterministic POSIX exit codes: `0` (Success), `1` (Runtime Fault), `2` (Security Breach), `3` (Circuit Breaker Interception / Iteration Ceiling) (COMP-09).
- [X] **Task 5.2: Enterprise Production Documentation (`README.md`)**
  - [X] Author portfolio-grade architectural documentation with system design diagrams.
  - [X] Document stream demultiplexing architecture (ADR-0013) with ASCII data flow illustrations.
  - [X] Document cgroups v2 container isolation and C-authorizer database security models.
  - [X] Include reproducible setup instructions for Ubuntu, macOS, and Windows/WSL2.
- [X] **Task 5.3: Verification of KPIs Against Acceptance Criteria**
  - [X] Measure P95 multi-tool execution latency; verify $\le 8.5\text{ seconds}$ on warm local Ollama Qwen 2.5 7B runs.
  - [X] Verify 100% loop break rate across test suites.
  - [X] Verify 0 unauthorized host OS operations across all test runs.
