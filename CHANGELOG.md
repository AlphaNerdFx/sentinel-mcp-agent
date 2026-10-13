# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.2.0] - 2026-10-13 (Phase 2 Milestone: State Machine Orchestration & Safety Guardrails)

### Added

* **Deterministic ReAct State Machine (`COMP-01`):** Implemented asynchronous LangGraph workflow (`src/agent/graph.py`, `src/agent/nodes.py`) compiling `agent`, `tools`, and `force_end` nodes with Write-Ahead Logging persistence via `AsyncSqliteSaver` targeting `.agent_state.db` (ADR-0017).
* **Native FastMCP Client Manager (`COMP-04 Client`):** Implemented `src/agent/mcp_client.py` using native `fastmcp.Client` and `StdioTransport` to spawn and manage child server processes over stdio. Dynamically synthesizes runtime Pydantic validation schemas via `pydantic.create_model()` to wrap MCP tools as LangChain `StructuredTool` instances (ADR-0019).
* **Commutative SQL AST Fingerprinting (`COMP-03`):** Implemented `canonical_fingerprint()` in `src/agent/state.py` featuring an AST visitor (`_canonicalize_ast`) that recursively sorts commutative binary equality operands (`exp.EQ`, `exp.NEQ`). Guarantees identical SHA-256 signatures for queries with inverted predicate syntax (e.g., `1 = id` vs `id = 1`) (ADR-0016).
* **Atomic Tool Partition & Dispatch Node (`COMP-01` / `COMP-03`):** Implemented unified `tool_node` in `src/agent/nodes.py`. Partitions parallel calls into safe vs tripped, injects synthetic `ToolMessage` instances for calls with $\ge 3$ strikes, executes safe calls via MCP client, and guarantees 100% `tool_call_id` wire compliance without dropping sibling calls (ADR-0018).
* **Physical Integration Test Harness:** Created `scripts/verify_phase2_live.py` validating end-to-end execution across local Ollama Qwen 2.5 7B, the out-of-process FastMCP server, and persistent SQLite checkpointing.

### Changed

* **MCP Client Architecture (ADR-0019 Supersedes ADR-11):** Purged `langchain-mcp-adapters` from `pyproject.toml` and runtime codebase. Replaced third-party adapter with native `fastmcp.Client`, resolving upstream dependency deadlocks with FastMCP 4.x and MCP 2.x.
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

### Performance & Benchmarks

* **Docker Cold-Start Overhead:** Empirical benchmarking across 5 sequential analytical cycles confirmed a P50 execution latency of 1,034.09 ms (Max 1,164.54 ms).
* **Timeout SLA Enforcement:** Verified hard-kill termination on infinite loops: scripts exceeding 5.0 seconds terminate with POSIX exit code 124.
* **Teardown Latency Lag:** Discovered a 1,583.49ms teardown lag resulting from WSL2 socket IPC translation and synchronous container removal.

---

## [0.0.1] - 2026-10-08 (Phase 0 Milestone: Environment & Toolchain Verification)

### Added

* Standalone environment verification script (`scripts/check_env.py`) validating NVIDIA GPU VRAM headroom ($\ge 1,000\text{ MB}$) using `nvidia-ml-py` with CLI fallback.
* Docker socket permission and cgroup constraint verification gate (`scripts/test_docker_socket.py`) confirming exit code 137 on memory exhaustion.
* PEP 621 packaging configuration in `pyproject.toml` and cryptographically locked `requirements.lock` via `pip-tools`.
* POSIX automation `Makefile` for environment checking, dependency locking, and test runs.
* Foundation architecture documentation: `PRD_V1.md`, `SPEC_V1.md`, `SECURITY.md`, `README.md`, `TODO.md`, and Apache 2.0 `LICENSE`.
* Architectural Decision Records: ADR-10 (Ollama Multi-Model Residency) and ADR-12 (Resilient GPU Telemetry).

### Fixed

* Addressed Ollama cold-start read timeout by implementing an explicit pre-warm stage with `keep_alive: -1`.
* Migrated deprecated `pynvml` dependency to `nvidia-ml-py`.
