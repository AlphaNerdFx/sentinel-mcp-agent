# Sentinel MCP Agent: Enterprise Tool-Calling Runtime with Observability

[![Python Version](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![Orchestration](https://img.shields.io/badge/Orchestrator-LangGraph%20FSM-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![Protocol](https://img.shields.io/badge/Protocol-Model%20Context%20Protocol%20(FastMCP%204.x)-purple.svg)](https://modelcontextprotocol.io/)
[![Hardware Target](https://img.shields.io/badge/Hardware%20Target-NVIDIA%20RTX%204060%20(8GB%20VRAM)-green.svg)](https://www.nvidia.com/)
[![Containment](https://img.shields.io/badge/Sandbox-cgroups%20v2%20Docker%20(--network%20none)-red.svg)](SECURITY.md)
[![Static Typing](https://img.shields.io/badge/Mypy-Strict%20(0%20Errors)-blueviolet.svg)](https://mypy-lang.org/)
[![License](https://img.shields.io/badge/License-Apache%202.0-lightgrey.svg)](LICENSE)

An enterprise-grade, deterministic tool-calling agent implementing Anthropic's **Model Context Protocol (MCP)** via **FastMCP** over standard I/O, coordinated by a deterministic **LangGraph Finite State Machine (FSM)**. 

Engineered for production data analytics, Sentinel executes untrusted model-generated Python inside a hardened, non-networked Linux cgroups v2 sandbox, queries relational databases through an OS-level read-only URI combined with an engine-level SQLite C-authorizer, intercepts semantic retry loops at Strike 3 via commutative AST canonicalization, checkpoints conversational state to an ACID SQLite WAL engine, and enforces POSIX stream demultiplexing with RFC 3339 JSON telemetry.

---

## 1. System Architecture & Finite State Machine (FSM)

[Certain] The runtime decouples cognitive planning from tool execution across operating system process boundaries via JSON-RPC 2.0. Stateful orchestration is modeled as an immutable, cyclic Directed Acyclic Graph (DAG) with pure asynchronous closures (SPEC COMP-01):

                    ┌──────────────────────────────────────────────┐
                    │      CLI Entrypoint / Subprocess Client      │
                    │                 (main.py)                    │
                    └──────────────────────┬───────────────────────┘
                                           │
                    Initial AgentState / thread_id (UUID)
                                           │
                                           ▼
     ┌───────────────────────────────────────────────────────────────────────────┐
     │             LANGGRAPH DETERMINISTIC FINITE STATE MACHINE (FSM)            │
     │                                                                           │
     │  Persistent Storage: .agent_state.db (AsyncSqliteSaver, WAL Mode)         │
     │                                                                           │
     │             ┌──────────────┐     iterations >= 10     ┌────────────────┐  │
     │    ┌───────►│  agent_node  ├─────────────────────────►│ force_end_node │  │
     │    │        │  (Ollama 7B) │                          │ (Terminal AIMsg│  │
     │    │        └──────┬───────┘                          └───────┬────────┘  │
     │    │               │                                          │           │
     │    │ Observation   │ Tool Calls Emitted                       │           │
     │    │ Ingestion     ▼                                          │           │
     │    │        ┌──────────────┐                                  │           │
     │    └────────┤  tool_node   │                                  ▼           │
     │             │ (Atomic Fan) │                             [__end__]        │
     │             └──────┬───────┘                                              │
     └────────────────────┼──────────────────────────────────────────────────────┘
                          │
                          │ JSON-RPC 2.0 over POSIX stdio pipes
                          │
                          ▼
     ┌───────────────────────────────────────────────────────────────────────────┐
     │                    FASTMCP ENTERPRISE TOOL SERVER                         │
     │                             (src/server.py)                               │
     │                                                                           │
     │     - Transport: stdio (Zero non-JSON-RPC bytes to stdout)                │
     │     - Diagnostic Logging: sys.stderr exclusively (ADR-0013)               │
     │     - Resource: schema://main                                             │
     │                                                                           │
     │      ┌──────────────────┬──────────────────┬──────────────────┐           │
     │      ▼                  ▼                  ▼                  ▼           │
     │  query_database     run_python         web_search      [Extensible Tools] │
     └──────┬──────────────────┬──────────────────┬──────────────────────────────┘
            │                  │                  │
            ▼                  ▼                  ▼
     ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
     │ SQLite C-Auth│   │ cgroups v2   │   │ Resilient    │
     │ Engine (ro)  │   │ Linux Box    │   │ Search Tier  │
     │              │   │              │   │              │
     │ - mode=ro URI│   │- net: none   │   │ 1. ddgs      │
     │ - C-Filter   │   │- 256MB RAM   │   │ 2. Tavily    │
     │ - Deny DML   │   │- ro root     │   │ 3. Brave     │
     │ - Deny ATTACH│   │- 5.0s kill   │   │ 4. Exhaust   │
     └──────────────┘   └──────────────┘   └──────────────┘

---

## 2. Stream Demultiplexing Architecture (ADR-0013)

[Certain] Conventional agent frameworks mix diagnostic logging with application output, corrupting JSON-RPC 2.0 framing over standard I/O pipes. Sentinel enforces strict **POSIX File Descriptor Demultiplexing**:

                                Operating System Process Boundary
                                                  │
                    ┌─────────────────────────────┴─────────────────────────────┐
                    ▼                                                           ▼
    ┌────────────────────────────────────────────        ┌─────────────────────────────────────────────┐
    |        File Descriptor 1 (stdout)         |        |       File Descriptor 2 (stderr)            | 
    |  STRICT PROTOCOL TRANSPORT CHANNEL        |        |    OBSERVABILITY & AUDIT CHANNEL            |
    |  ─────────────────────────────────────────|        |─────────────────────────────────────────────| 
    |  • CLI Mode: Clean synthesized answer text|        |  • 100% of telemetry events emitted as      |
    |  (Pure text output; zero JSON framing).   |        |  • single-line RFC 3339 JSON records.       |
    |  • Server Mode: Valid JSON-RPC 2.0 frames |        |  • Subsystem startup diagnostics & traces.  |
    |  strictly adhering to MCP specifications. |        |  • Circuit-breaker trip notices.            |
    |  • Zero debugging bytes permitted.        |        | • Shadow cloud billing ledger.              |
    ┴────────────────────────────┴──────────────┴        ┴─────────────────────────────────────────────┴ 

### Downstream Unix Piping Verification
Because `stdout` is physically segregated from diagnostic logs, the CLI composes cleanly with standard Unix streaming pipelines:
```bash
# Capture raw analytical answer without log corruption
python main.py "Calculate Q3 revenue" > response.txt 2> telemetry.jsonl

# Process answer with standard text tools
cat response.txt | jq .
```
## 3. Defense-in-Depth Security Models
Sentinel does not rely on soft LLM prompt guardrails to prevent system exploitation. Security is enforced through kernel-level and engine-level hard boundaries:
DEFENSE-IN-DEPTH SECURITY PERIMETER
                                             │
         ┌───────────────────────────────────┴───────────────────────────────────┐
         ▼                                                                       ▼
   CODE EXECUTION SANDBOX (COMP-05)                               DATABASE ACCESS ENGINE (COMP-06)
   Linux Kernel cgroups v2 Isolation                              SQLite C-Engine Bytecode Authorizer
   ─────────────────────────────────                              ───────────────────────────────────
   • Network Stack: --network none                                • Filesystem: URI file:db.db?mode=ro
     (Kernel denies socket creation: Errno 101).                    (OS kernel VFS write prohibition).
   • Memory Limit: 256 MB cgroup ceiling                          • C-Authorizer: sqlite3.set_authorizer
     (Instant OOM-killer termination: Exit code 137).               evaluates raw bytecode before compilation.
   • CPU Quota: 1.0 cores (CFS quota: 100,000 / 100,000us).       • Permitted Actions:
   • Root Filesystem: read_only=True                                SQLITE_SELECT, SQLITE_READ, SQLITE_FUNCTION.
     (Kernel blocks writes: Errno 30 EROFS / Errno 13).           • Blocked Actions:
   • Scratchpad: tmpfs={"/tmp": "rw,size=16m"}.                     DROP, DELETE, UPDATE, INSERT, ALTER, ATTACH.
   • Teardown: Unconditional stop_timeout=0 force-kill.           • Transpilation: Caught and transpiled to
                                                                    conversational refusal strings for LLM.

## 4. Commutative AST Circuit Breaker (ADR-0016 / ADR-0018)
[Certain] Stochastic agents enter infinite loops when tools return errors, generating semantically identical queries with minor syntactic variations. Sentinel canonicalizes queries at the Abstract Syntax Tree (AST) layer:
```text
Fingerprint=SHA256(tool_name+":"+CanonicalizeAST(raw_sql))
```
Raw LLM Query Variations
                                          │
            ┌─────────────────────────────┼─────────────────────────────┐
            ▼                             ▼                             ▼
    WHERE 10 = id AND active=1     WHERE id = 10 AND 1=active     WHERE active=1 AND id=10
            │                             │                             │
            └─────────────────────────────┼─────────────────────────────┘
                                          │
                                          ▼
                         sqlglot Bottom-Up AST Normalizer
                         - Inverts relational operators (10 = id -> id = 10)
                         - Normalizes binary equality (exp.EQ, exp.NEQ)
                         - Lexicographically sorts boolean junctions (AND, OR)
                                          │
                                          ▼
                      Canonical AST: WHERE active = 1 AND id = 10
                                          │
                                          ▼
                      Deterministic SHA-256 Digest: 9a7f4b82...

### Atomic Partition Fan-Out Tool Dispatch (ADR-0018)
When a canonical fingerprint reaches Strike 3, tool_node atomically intercepts execution:
Tripped calls are bypassed; a synthetic ToolMessage(content="CIRCUIT BREAKER TRIGGERED: ...") fulfills the exact tool_call_id.
Safe sibling tool calls execute in parallel through the FastMCP client.
100% of model-requested tool_call_ids are fulfilled in a single turn, eliminating upstream HTTP 400: missing tool_call_id wire protocol crashes.
## 5. Persistent State & Session Resumption (ADR-0017)
[Certain] State persistence is backed by AsyncSqliteSaver targeting .agent_state.db using SQLite Write-Ahead Logging (PRAGMA journal_mode=WAL;).
Atomic State Snapshots: Every FSM superstep writes an isolated state snapshot indexed by thread_id (session_id).
Session Resumption: Conversations can be suspended, process-terminated, and resumed hours later from disk using --session-id <UUID> without context loss.
Concurrency Protection: Connection pools configure PRAGMA busy_timeout = 5000; to prevent file-locking deadlocks across concurrent CLI invocations.
### 6. Hardware Budget & VRAM Allocation Ledger
[Certain] Benchmarked and verified on an NVIDIA GeForce RTX 4060 Laptop GPU (8,192 MB GDDR6 physical VRAM):
|Component	|Footprint	|Allocation Type	|Architectural Purpose|
| :------ | :-------- | :------------------------------------------------------ |:------------------------------------------------------ |
|Host OS & Desktop GUI |	~800 MB	| Static System	|Display server and driver overhead.|
|CUDA Runtime & Buffers	|~500 MB	|Static System	|cuBLAS, cuDNN context memory pools.|
|Qwen 2.5 7B Instruct (Q4_K_M)	|~4,400 MB|	Static Model	|Primary reasoning & tool-calling engine.|
|nomic-embed-text-v1.5 (Q4_K)|	~280 MB	|Static Model|	Local dense embedding model.|
|KV Cache (8,192 Context Window)|	~1,200 MB	|Dynamic Runtime|	Multi-turn conversational attention state.|
|Active Allocation Total|	~7,180 MB	|System Active|	Fits 100% within 8GB VRAM.|
|Unallocated Crash Buffer|	~1,012 MB	|Safety Margin|	Headroom preventing CUDA OOM kernel halts.|

## 7. OS-Specific Setup & Installation
### System Prerequisites
* Python: Python 3.11.x (Strict requirement).
* Container Runtime: Docker Engine 24.x+ or Docker Desktop with /var/run/docker.sock access.
* Local Inference: Ollama 0.3.x+ installed and listening on http://localhost:11434.
### Installation Paths
* Linux (Ubuntu 22.04 / 24.04 LTS)
```bash
# 1. Install system dependencies
sudo apt update && sudo apt install -y python3.11 python3.11-venv sqlite3 docker.io

# 2. Grant non-root Docker socket permissions
sudo usermod -aG docker $USER && newgrp docker

# 3. Clone repository and initialize environment
git clone https://github.com/your-username/sentinel-mcp-agent.git
cd sentinel-mcp-agent
python3.11 -m venv .venv
source .venv/bin/activate

# 4. Install cryptographically locked dependencies
pip install --upgrade pip pip-tools
pip-sync requirements.lock
```
* macOS (Apple Silicon: M1 / M2 / M3 / M4)
```bash
# 1. Install dependencies via Homebrew
brew install python@3.11 sqlite3 ollama

# 2. Start Docker Desktop and ensure socket is exposed:
# Docker Desktop -> Settings -> Advanced -> Allow default Docker socket (/var/run/docker.sock)

# 3. Clone and initialize
git clone https://github.com/your-username/sentinel-mcp-agent.git
cd sentinel-mcp-agent
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip pip-tools
pip-sync requirements.lock
```
* Windows 11 with WSL2 (CRITICAL FILESYSTEM WARNING)
```text
CRITICAL ARCHITECTURAL REQUIREMENT FOR WSL2 USERS:
You MUST clone and run this repository inside the native Linux ext4 filesystem (/home/username/...).
NEVER run this project from Windows mounts (/mnt/c/...). Accessing SQLite databases and model context across the Windows 9P hypervisor bridge degrades disk I/O by 50x, turning a 2-second inference pass into a 5-minute kernel stall.
```
```bash
# Open WSL2 Ubuntu terminal:
cd /home/$USER
git clone https://github.com/your-username/sentinel-mcp-agent.git
cd sentinel-mcp-agent

python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip pip-tools
pip-sync requirements.lock
```
### Provision Model Artifacts & Permanent VRAM Residency
```bash
# Pull model artifacts to local daemon
ollama pull qwen2.5:7b-instruct-q4_K_M
ollama pull nomic-embed-text:v1.5

# Pre-warm weights and enforce indefinite VRAM residency (ADR-0010)
ollama run qwen2.5:7b-instruct-q4_K_M "ping"
ollama ps  # Verify 100% GPU residency
```
## 8. CLI Application Usage Guide (COMP-09)
The application provides a deterministic command-line interface with standardized POSIX exit codes:
* 0: Success (Conversational goal achieved or handled refusal).
* 1: Runtime Fault (Invalid parameters, missing dependencies).
* 2: Unhandled Security Breach.
* 3: Circuit Breaker Abort / Iteration Ceiling reached (iterations >= 10).
### 1. One-Shot Prompt Mode
```bash
# Execute an analytical query against local SQLite
python main.py "Search the database for CloudEngine Q1 revenue and return ONLY the numeric value."
# Output: 1250000.0 (Exit code: 0)
```
### 2. Interactive Multi-Turn REPL Mode
```bash
python main.py --interactive
# Boots stateful session. Maintains conversational history across turns.
# Exit using ':q', 'quit', or 'exit'.
```
### 3. Session Resumption Mode
```bash
# Resume an existing session from .agent_state.db across independent OS processes
python main.py --session-id "99116dec-5a50-4355-989c-b2b3796ca541" "Now project that revenue with a 15% increase."
```
### 4. Real-Time Telemetry Mode
```bash
# Output clean answer to terminal while viewing real-time latency traces on stderr
python main.py --verbose "Calculate CloudEngine growth"
```
## 9. Verification Suite & CI/CD Pipeline
The repository enforces 100% hermetic verification across static analysis, unit tests, and black-box OS subprocess integration:
```bash
# 1. Static Type Certification (Strict Mypy - 0 errors across 18 source modules)
.venv/bin/mypy src/ main.py tests/

# 2. Style & Linter Certification (Ruff - 100% compliance)
.venv/bin/ruff check src/ main.py tests/
.venv/bin/ruff format --check src/ main.py tests/

# 3. Unit Verification Suite (54 Tests executing in < 10 seconds)
.venv/bin/pytest tests/unit/ -v

# 4. User Story End-to-End Tests (US-01, US-02, US-03)
.venv/bin/pytest tests/e2e/test_us01_multistep_query.py tests/e2e/test_us02_loop_interception.py tests/e2e/test_us03_security_containment.py -v

# 5. Black-Box OS Process Integration Suite (Validates exit codes & streams)
.venv/bin/pytest tests/e2e/test_cli_e2e.py -v
```
## 10. Architectural Decision Records (ADRs)
For deep design justifications, consult docs/PRD_V1.md and docs/SPEC_V1.md:
* ADR-0001: Orchestration via LangGraph Deterministic FSM.
* ADR-0002: Tool Transport via FastMCP stdio JSON-RPC 2.0.
* ADR-0003: Linux cgroups v2 Container Sandbox Isolation.
* ADR-0004: Pinned Local Inference via Ollama Qwen 2.5 7B.
* ADR-0007: 3-Tier Resilient Search Cascade (ddgs → Tavily → Brave → Exhausted).
* ADR-0010: Permanent VRAM Model Residency (keep_alive: -1).
* ADR-0013: POSIX Stream Demultiplexing (stdout JSON-RPC / Text vs. stderr Telemetry).
* ADR-0014: SQLite C-Engine Bytecode Authorizer Integration.
* ADR-0016: Commutative AST Semantic Loop Breaker (sqlglot).
* ADR-0017: Durable State Checkpointing via Async SQLite WAL (.agent_state.db).
* ADR-0018: Atomic Partition & Fan-Out Tool Dispatch Node.
* ADR-0019: Native FastMCP Client Integration without Third-Party Adapters.