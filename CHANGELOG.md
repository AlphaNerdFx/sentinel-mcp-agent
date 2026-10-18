# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2026-10-18 - Version 1.0.0 Production Release

### Added
- **Zero-Config CLI Gateway (`main.py`):** Standalone entrypoint supporting one-shot prompts, stateful multi-turn interactive REPL (`--interactive`), session resumption from disk (`--session-id <UUID>`), and real-time colorized telemetry (`--verbose`).
- **Deterministic POSIX Status Codes:** Explicit exit code signaling (0=Success, 1=Runtime Fault, 2=Security Violation, 3=Iteration Ceiling).
- **Subprocess Integration Test Suite (`tests/e2e/test_cli_e2e.py`):** Black-box tests asserting OS stream segregation (clean stdout, valid JSON stderr) and cross-process SQLite state resumption across distinct operating system PIDs.
- **Empirical KPI Verification Harness (`scripts/benchmark_kpis.py`):** Automated statistical benchmark capturing P50/P90/P95 latency distributions, validating 100% circuit-breaker interception, and asserting 0 host mutations via pre/post SHA-256 file hashing.
- **Production Portfolio Documentation (`README.md`):** Complete enterprise architecture documentation including ASCII stream demultiplexing trees, cgroups v2 container isolation specifications, SQLite C-authorizer security boundaries, and OS-specific setup guides with WSL2 9P filesystem warnings.

### Changed
- **Ephemeral System Prompt Invariant (`src/agent/nodes.py`):** Injected runtime UTC temporal anchors and domain-agnostic Semantic Role Labeling (SRL) rules to prevent temporal staleness, predecessor-successor attention collapse, and instruction mimicry.
- **FastMCP Stdio Robustness (`src/server.py`):** Bootstrapped `sys.path[0]` dynamically on startup to eliminate `ModuleNotFoundError` crashes during standalone script and subprocess execution outside GNU Make.
- **Telemetry Context Propagation (`src/telemetry/logger.py`):** Implemented `contextvars.ContextVar` ambient context tracking and keyword parameter overrides, guaranteeing 100% session ID propagation across all state-machine transitions.

### Verified Physical Metrics
- **P95 Execution Latency:** 4.67 seconds (SLA: $\le 8.5\text{s}$ under warm Ollama Qwen 2.5 7B).
- **Loop Mitigation Rate:** 100.0% intercepted at Strike 3 via commutative AST canonicalization.
- **Security Perimeter:** 0 unauthorized host operations across destructive SQL DDL/DML and Docker socket jailbreaks.

## [0.4.0] - 2026-10-16 (Phase 4 Milestone: Automated Verification Suite & CI/CD Pipeline)

### Added

* **Automated CI/CD Pipeline (`.github/workflows/ci.yml`):** Implemented remote GitHub Actions workflow on Ubuntu runners with Docker service integration, executing full static analysis, unit test suites, stream demultiplexing checks, and end-to-end user story verification on every push and pull request.
* **Hermetic Unit Test Suite (54 Tests across `tests/unit/`):**
  * `tests/unit/agent/test_loop_detector.py`: 10 tests verifying commutative AST binary equality (`exp.EQ`, `exp.NEQ`), relational inversion (`exp.GT`, `exp.LT`), boolean conjunctions (`exp.And`), boolean disjunctions (`exp.Or`), whitespace/casing normalization, subqueries, and JSON parameter sorting (ADR-0016).
  * `tests/unit/agent/test_model_adapter.py`: 5 tests verifying local Ollama daemon probes, cloud fallback to `gpt-4o-mini`, and transport deadline resolution (`MODEL_TIMEOUT=120.0s`).
  * `tests/unit/agent/test_state_graph.py`: 5 tests verifying the 3-node FSM topology (`agent`, `tools`, `force_end`), conditional edge routing via `route_agent_output`, and the 10-iteration ceiling cutoff (ADR-0001).
  * `tests/unit/agent/test_telemetry_schema.py`: 4 tests validating single-line JSON emission strictly to `sys.stderr`, RFC 3339 timestamp parsing, shadow cloud billing calculation ($0.15/$0.60 per 1M tokens), and guaranteed `session_id` context propagation (ADR-0013, ADR-0009).
  * `tests/unit/tools/test_mcp_server.py`: 6 tests validating out-of-process FastMCP server execution over stdio, tool dispatch, and DDL resource registry (`schema://main`).
  * `tests/unit/tools/test_sandbox_security.py`: 6 tests validating Docker container cgroup memory limits (256MB), network blocking (`--network none`), 5.0-second timeout enforcement, and Linux VFS kernel write denial (`EROFS` 30 / `EACCES` 13) (ADR-0003).
  * `tests/unit/tools/test_search_fallback.py`: 5 tests validating Chain-of-Responsibility fallback across DuckDuckGo, Tavily, and Brave Search, and graceful degradation to `Exhausted` (ADR-0007).
  * `tests/unit/tools/test_sql_guardrails.py`: 13 tests validating SQLite C-level authorizer denial of DDL (`DROP`), DML (`DELETE`, `UPDATE`), system PRAGMAs, and database smuggling (`ATTACH`) (ADR-0014).
* **End-to-End User Story Integration Suite (4 Tests across `tests/e2e/`):**
  * `test_us01_multistep_query.py`: Verifies US-01 multi-step analytical execution (SQL data fetch $\rightarrow$ Python 15% projection $\rightarrow$ Synthesis in $\le 4$ iterations).
  * `test_us02_loop_interception.py`: Verifies US-02 circuit-breaker Strike 3 interception, synthetic `ToolMessage` injection, and 100% `tool_call_id` wire compliance without dropping calls (ADR-0018).
  * `test_us03_security_containment.py`: Verifies US-03 state-machine containment of destructive SQL commands and container network exfiltration attempts.
* **Production Automation Makefile:** Implemented comprehensive `Makefile` featuring `make ci`, `make lint`, `make lint-fix`, `make test-unit`, `make test-e2e`, and `make clean`.
* **Repository Normalization (`.gitattributes`):** Locked LF line-ending normalization across all Python, shell, toml, and markdown files to prevent Windows CRLF (`^M`) corruption in WSL2 and CI.

### Changed

* **Repository Re-Branding:** Crystallized official project repository name as `sentinel-mcp-agent` to reflect safety, containment, and circuit-breaking capabilities.
* **ADR Numbering Normalization:** Formally mapped and standardized all Architectural Decision Records into unified 4-digit notation (`ADR-0001` through `ADR-0019`) across all documentation.
* **Strict Static Typing Certification:** Achieved 100% clean static type checking across all 17 source modules under Mypy, resolving dynamic schema assignment narrowing and AST node covariance.
* **Relational Database Self-Seeding:** Updated `DatabaseEngine` in `src/tools/database.py` to auto-seed `company_metrics.db` if missing, guaranteeing hermetic execution on clean checkout environments.
* **Search Cascade Credential Pre-Checks:** Hardened `ResilientSearchEngine.search()` to evaluate API key presence before invoking commercial tiers, preventing mock leakage in unit tests.
* **Telemetry Session Defaults:** Enhanced `StructuredLogger` to guarantee `session_id` context propagation, eliminating un-indexed audit records.

### Fixed

* **AST In-Place Pointer Aliasing:** Fixed critical corruption bug in `src/agent/state.py` where in-place operand swapping caused child nodes to overwrite their sibling references (`WHERE 10 = id` $\rightarrow$ `WHERE id = id`). Migrated to `sqlglot.transform` visitor pattern.
* **GNU Make Shell Word-Splitting (Error 127):** Fixed `/bin/bash: line 1: /mnt/c/DSC/Career/Projects/ReAct: No such file or directory` by replacing absolute `$VIRTUAL_ENV` expansions with the relative path `.venv/bin/python3`.
* **Make Clipboard Separator Corruption:** Fixed `Makefile: *** missing separator` by authoring Makefiles programmatically with literal ASCII Tab (`0x09`) bytes.
* **Remote Runner Missing Dependencies:** Resolved `No module named ruff` in GitHub Actions by compiling `requirements.lock` with `--extra=dev`.
* **SQLite URI Read-Only Lockout:** Resolved `unable to open database file` under URI `mode=ro` by creating and seeding the database file before read-only descriptors are acquired.
* **CPython Entrypoint `sys.path[0]` Inversion:** Fixed `ModuleNotFoundError: No module named 'src'` during direct script execution by exporting `PYTHONPATH := .` across Makefile recipes.
* **Flake8-Bugbear B904 Chaining:** Added explicit `from err` and `from exc` chaining across database and sandbox drivers to preserve causal exception tracebacks.
* **Pydantic `Optional` Import Shadowing:** Fixed `Value of type 'object' is not indexable` by importing `Optional` strictly from standard library `typing`.
* **Uncompiled StateGraph Execution:** Fixed `AttributeError: 'StateGraph' object has no attribute 'ainvoke'` in E2E tests by calling `.compile()` on graph workflows before invocation.

---

## [0.2.0] - 2026-10-13 (Phase 2 Milestone: State Machine Orchestration & Safety Guardrails)

### Added

* **Deterministic ReAct State Machine (`COMP-01`):** Implemented asynchronous LangGraph workflow (`src/agent/graph.py`, `src/agent/nodes.py`) compiling `agent`, `tools`, and `force_end` nodes with Write-Ahead Logging persistence via `AsyncSqliteSaver` targeting `.agent_state.db` (ADR-0017).
* **Native FastMCP Client Manager (`COMP-04 Client`):** Implemented `src/agent/mcp_client.py` using native `fastmcp.Client` and `StdioTransport` to spawn and manage child server processes over stdio. Dynamically synthesizes runtime Pydantic validation schemas via `pydantic.create_model()` to wrap MCP tools as LangChain `StructuredTool` instances (ADR-0019).
* **Commutative SQL AST Fingerprinting (`COMP-03`):** Implemented `canonical_fingerprint()` in `src/agent/state.py` featuring an AST visitor (`_canonicalize_ast`) that recursively sorts commutative binary equality operands (`exp.EQ`, `exp.NEQ`) (ADR-0016).
* **Atomic Tool Partition & Dispatch Node (`COMP-01` / `COMP-03`):** Implemented unified `tool_node` in `src/agent/nodes.py`. Partitions parallel calls into safe vs tripped, injects synthetic `ToolMessage` instances for calls with $\ge 3$ strikes, executes safe calls via MCP client, and guarantees 100% `tool_call_id` wire compliance without dropping sibling calls (ADR-0018).
* **Physical Integration Test Harness:** Created `scripts/verify_phase2_live.py` validating end-to-end execution across local Ollama Qwen 2.5 7B, the out-of-process FastMCP server, and persistent SQLite checkpointing.

### Changed

* **MCP Client Architecture (ADR-0019 Supersedes ADR-0011):** Purged `langchain-mcp-adapters` from `pyproject.toml` and runtime codebase. Replaced third-party adapter with native `fastmcp.Client`, resolving upstream dependency deadlocks with FastMCP 4.x and MCP 2.x.
* **State Schema Optimization:** Refactored `AgentState["tool_call_history"]` in `src/agent/state.py` from `List[str]` to `dict[str, int]` for $O(1)$ strike threshold tracking.
* **Pure Asynchronous Closures:** Refactored `build_agent_workflow()` in `src/agent/graph.py` to bind node dependencies via explicit `async def` inner closures, preserving Python `CO_COROUTINE` reflection flags required by LangGraph.
* **Inference Transport Deadline:** Configured `MODEL_TIMEOUT` environment resolution with a 120.0-second default in `src/agent/model_adapter.py` to prevent false-positive socket drops during GBNF grammar compilation and WSL2 TTFT latency.
* **Telemetry Method Standardization:** Updated `StructuredLogger` in `src/telemetry/logger.py` to expose `log_event(event_type, node, metrics, payload)` emitting strictly to `sys.stderr` (ADR-0013).

### Fixed

* **SAT Solver Dependency Deadlock:** Resolved `pip-compile` `ResolutionImpossible` error caused by conflicting version requirements between `mcp<2.0.0` (from `langchain-mcp-adapters`) and `mcp>=2.0.0` (from `fastmcp-slim 4.0.11`).
* **Async Checkpoint Engine Crash:** Fixed `ModuleNotFoundError: No module named 'langgraph.checkpoint.sqlite'` and `NotImplementedError` by migrating from synchronous `SqliteSaver` to `AsyncSqliteSaver` managed via async context managers.
* **State Reducer Coroutine Type Error:** Fixed `langgraph.errors.InvalidUpdateError: Expected dict, got <coroutine object>` by eliminating synchronous lambdas that failed to await async node functions.
* **Local Inference Socket Read Timeout:** Fixed `httpcore2.ReadTimeout` / `openai.APITimeoutError` by eliminating the hardcoded 30-second socket timeout on non-streaming local inference calls.
* **Commutative Hash Drift:** Fixed `AssertionError` in SQL loop detection where `id = 1` and `1 = id` produced different SHA-256 digests.
* **Script Module Import Path Bleed:** Fixed `ModuleNotFoundError: No module named 'src'` in standalone script runners by injecting deterministic repository root anchoring into `sys.path`.
* **Telemetry Facade Import Error:** Fixed `ImportError: cannot import name 'CostEngine'` by standardizing class contracts in `src/telemetry/cost.py`.

---

## [0.1.0] - 2026-10-09 (Phase 1 Milestone: Tool Engine & Isolation Primitives)

### Added

* **FastMCP Tool Server (`COMP-04`):** Implemented `src/server.py` serving database retrieval, Docker sandboxing, and web search over stdio JSON-RPC 2.0 transport. Exposes database DDL as an MCP resource (`schema://main`) to prevent turn consumption during schema discovery.
* **Docker Isolation Sandbox (`COMP-05`):** Implemented `src/sandbox/docker_runner.py` managing ephemeral container lifecycles via the Docker Engine API socket (`/var/run/docker.sock`). Enforces non-root execution (`user="nobody"`), `--network none`, `--memory 256m`, `--cpus 1.0`, `--read-only`, and tmpfs scratchpads at `/tmp:rw,size=16m`.
* **Relational Database Engine (`COMP-06`):** Implemented `src/tools/database.py` managing embedded SQLite storage (`company_metrics.db`), automated schema seeding, and read-only query execution.
* **Resilient Multi-Provider Search (`COMP-07`):** Implemented `src/tools/search.py` deploying a 3-tier Chain of Responsibility cascade: DuckDuckGo (Tier 1 scrape) $\rightarrow$ Tavily API (Tier 2 authenticated) $\rightarrow$ Brave Search API (Tier 3 authenticated) $\rightarrow$ Exhausted Null Object. Normalizes all provider payloads into strict Pydantic models (`UnifiedSearchResponse`, `SearchResultItem`).
* **Structured Telemetry & Cost Engine (`COMP-08`):** Implemented `src/telemetry/logger.py` and `src/telemetry/cost.py` emitting RFC 3339-compliant, single-line JSON events tracking execution latencies, token consumption, and simulated commercial API costs ($0.15/$0.60 per million tokens).
* **Live Benchmarking Harness:** Created `scripts/verify_phase1_live.py` to evaluate live SQLite URI locks, Docker SLA conformance, authenticated search APIs, and Pydantic schema validation.
* **Hermetic Unit Test Suite:** Authored unit tests across `tests/unit/` covering primitive execution, error branches, and fallback behavior.

### Changed

* **Runtime Stack Modernization (ADR-0015):** Upgraded core dependencies to modern LTS releases: `langchain-core 1.6.7`, `langgraph 1.2.14`, `fastmcp 4.0.11`, `mcp 2.3.0`, and `sqlglot 30.21.0`. Eliminated unresolvable 0.x package solver conflicts.
* **Metadata Query Convention:** Standardized runtime package version checks on Python 3.11 standard library `importlib.metadata.version()` to accommodate modern packages that omit `__version__` on their root package namespace.
* **Test Runner Convention:** Enforced invoking pytest strictly as `python -m pytest` inside active `.venv` to prevent environment bleed from host Python interpreters.

### Security

* **SQLite Dual-Layer Defense (ADR-0014):** Hardened query execution by coupling SQLite URI read-only mode (`file:...mode=ro`) with a C-engine authorizer callback (`sqlite3.Connection.set_authorizer`). Blocks `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, and `ATTACH` statements before query evaluation.
* **Stdio Transport Stream Hygiene (ADR-0013):** Enforced stream demultiplexing across all subsystems: `sys.stdout` is reserved exclusively for FastMCP JSON-RPC 2.0 frames; all diagnostic logs, error tracebacks, and telemetry events route strictly to `sys.stderr`.
* **Kernel-Level Sandboxing:** Enforced Linux namespace and cgroup boundaries inside Docker containers. Outbound network attempts fail at the kernel level (`Network is unreachable`), and memory allocation bombs trigger immediate terminations via exit code 137.

---

## [0.0.1] - 2026-10-08 (Phase 0 Milestone: Environment & Toolchain Verification)

### Added

* Standalone environment verification script (`scripts/check_env.py`) validating NVIDIA GPU VRAM headroom ($\ge 1,000\text{ MB}$) using `nvidia-ml-py` with CLI fallback.
* Docker socket permission and cgroup constraint verification gate (`scripts/test_docker_socket.py`) confirming exit code 137 on memory exhaustion.
* PEP 621 packaging configuration in `pyproject.toml` and cryptographically locked `requirements.lock` via `pip-tools`.
* POSIX automation `Makefile` for environment checking, dependency locking, and test runs.
* Foundation architecture documentation: `PRD_V1.md`, `SPEC_V1.md`, `SECURITY.md`, `README.md`, `TODO.md`, and Apache 2.0 `LICENSE`.
* Architectural Decision Records: ADR-0010 (Ollama Multi-Model Residency) and ADR-0012 (Resilient GPU Telemetry).

### Fixed

* Addressed Ollama cold-start read timeout by implementing an explicit pre-warm stage with `keep_alive: -1`.
* Migrated deprecated `pynvml` dependency to `nvidia-ml-py`.
