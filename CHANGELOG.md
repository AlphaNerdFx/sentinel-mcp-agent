# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.0.0] - 2026-10-07 (Phase 0 Milestone: Environment & Toolchain Verification)

### Added

* Environment verification script `scripts/check_env.py` validating RTX 4060 GPU VRAM headroom ($\ge 1,000\text{ MB}$) and Ollama model residency.
* Docker socket permission and cgroup validation gate `scripts/test_docker_socket.py`.
* PEP 621 `pyproject.toml` and cryptographically locked `requirements.lock`.
* Initial architecture documentation: `PRD_V1.md`, `SPEC_V1.md`, `SECURITY.md`, `README.md`, `TODO.md`, and Apache 2.0 `LICENSE`.

---

## [0.0.0] - 2026-10-08

### Added

- Phase 0 hardware and environment validation script (`scripts/check_env.py`) with NVML and CLI fallbacks.
- Python Docker SDK socket and cgroup constraint verification gate (`scripts/test_docker_socket.py`).
- PEP 621 compliant `pyproject.toml` and cryptographically locked `requirements.lock`.
- POSIX automation `Makefile` for environment checking, dependency locking, and test runs.
- Production `.gitignore` excluding SQLite databases, credentials, and build caches.
- Architectural Decision Records: ADR-10 (Ollama Multi-Model Residency), ADR-11 (MCP Stdio Client Bridge), and ADR-12 (Resilient GPU Telemetry).

### Fixed

- Addressed Ollama cold-start read timeout by implementing an explicit pre-warm stage with `keep_alive: -1`.
- Migrated deprecated `pynvml` dependency to `nvidia-ml-py`.

---

## [0.1.0] - 2026-10-09 (Phase 1 Milestone: Tool Engine & Isolation Primitives)

### Added

* **FastMCP Tool Server (`COMP-04`):** Implemented `src/server.py` serving database retrieval, Docker sandboxing, and web search over stdio JSON-RPC 2.0 transport. Exposes database DDL as an MCP resource (`schema://main`) to prevent turn consumption during schema discovery.
* **Docker Isolation Sandbox (`COMP-05`):** Implemented `src/sandbox/docker_runner.py` managing ephemeral container lifecycles via the Docker Engine API socket (`/var/run/docker.sock`). Enforces non-root execution (`user="nobody"`), `--network none`, `--memory 256m`, `--cpus 1.0`, `--read-only`, and tmpfs scratchpads at `/tmp:rw,size=16m`.
* **Relational Database Engine (`COMP-06`):** Implemented `src/tools/database.py` managing embedded SQLite storage (`company_metrics.db`), automated schema seeding, and read-only query execution.
* **Resilient Multi-Provider Search (`COMP-07`):** Implemented `src/tools/search.py` deploying a 3-tier Chain of Responsibility cascade: DuckDuckGo (Tier 1 scrape) $\rightarrow$ Tavily API (Tier 2 authenticated) $\rightarrow$ Brave Search API (Tier 3 authenticated) $\rightarrow$ Exhausted Null Object. Normalizes all provider payloads into strict Pydantic models (`UnifiedSearchResponse`, `SearchResultItem`).
* **Structured Telemetry & Cost Engine (`COMP-08`):** Implemented `src/telemetry/logger.py` and `src/telemetry/cost.py` emitting RFC 3339-compliant, single-line JSON events tracking execution latencies, token consumption, and simulated commercial API costs ($0.15/$0.60 per million tokens).
* **Semantic AST Circuit Breaker (`COMP-03`):** Implemented `src/agent/circuit_breaker.py` featuring Abstract Syntax Tree (AST) query parsing and transpilation via `sqlglot` to catch formatting drift and prevent repetitive loop attacks.
* **Live Benchmarking Harness:** Created `scripts/verify_phase1_live.py` to evaluate live SQLite URI locks, Docker SLA conformance, authenticated search APIs, and Pydantic schema validation.
* **Hermetic Unit Test Suite:** Authored 15 unit tests across `tests/unit/` covering primitive execution, error branches, and fallback behavior.

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
* **Teardown Latency Lag:** Discovered a 1,583.49ms teardown lag (total termination time 6,583.49 ms) resulting from WSL2 socket IPC translation and synchronous container removal.

### Technical Debt & Known Limitations

* **Upstream Search Library Deprecation:** `duckduckgo_search` emitted a runtime warning advising migration to `ddgs`. Migration scheduled for Phase 5.
* **Docker Timeout Teardown Optimization:** The 1.58s teardown lag threatens the P95 latency SLA. Optimization via `stop_timeout=0` and non-blocking background garbage collection scheduled for Phase 5.
* **Unit Test Duration:** The unit test suite takes ~19.25 seconds due to live Docker container execution in unit modules. Gating container tests behind `-m e2e` marks scheduled for Phase 5.
