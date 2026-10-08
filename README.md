# Enterprise MCP Tool-Calling Agent with Observability

[![Python Version](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![Architecture](https://img.shields.io/badge/Architecture-LangGraph%20StateGraph-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![Protocol](https://img.shields.io/badge/Protocol-Model%20Context%20Protocol%20(MCP)-purple.svg)](https://modelcontextprotocol.io/)
[![Hardware Target](https://img.shields.io/badge/Target%20GPU-RTX%204060%20Laptop%20(8GB%20VRAM)-green.svg)](https://www.nvidia.com/)
[![Security Profile](https://img.shields.io/badge/Sandbox-Docker%20Daemon%20Socket%20(--network%20none)-red.svg)](SECURITY.md)
[![License](https://img.shields.io/badge/License-Apache%202.0-lightgrey.svg)](LICENSE)

An enterprise-grade, deterministic tool-calling agent implementing Anthropic's **Model Context Protocol (MCP)** and orchestrated via **LangGraph StateGraph**. Designed specifically for analytical reasoning, the system executes untrusted Python code inside an ephemeral, non-networked Docker sandbox, queries relational databases through an engine-level read-only URI interface, prevents repetitive failure loops via SHA-256 signature fingerprinting, and emits structured JSON telemetry to `stdout` with shadow cloud cost modeling.

---

## 1. System Architecture Topology

[Certain] The system decouples cognitive orchestration from tool execution across strict process and security boundaries using JSON-RPC 2.0 over standard I/O (`stdio`):

| DATA FLOW ARCHITECTURE |
| | CLI User / | |
| | Automated Test | |
| | |
| User Prompt | Exit Code & JSON Logs |
| v |
| +---------------------------------------------------------------------------------------------+ |
| | LANGGRAPH AGENT ORCHESTRATOR (Deterministic Finite State Machine) | |
| | | |
| | +----------------+ Conditional Routing +------------------+ Repeat Count >= 3 | |
| | | Agent Node | --------------------------> | SHA-256 Circuit | --------------------+ | |
| | | (LLM Reason) | | Breaker Guard | | | |
| | +----------------+ +------------------+ | | |
| | ^ | | | |
| | | Observation Ingestion | Valid Tool Call | | |
| | +--------------------+ v | | |
| | | +------------------+ | | |
| | +---------------- | Tools Node | | | |
| | | (FastMCP Client) | | | |
| | +------------------+ | | |
| | | | | |
| | Iterations >= 10 | | | |
| | +------------------+ <-----------------------------------+ | | |
| | | Force End Node | | | |
| | | (Safe Fallback) | <------------------------------------------------------------------+ | |
| +--+------------------+-----------------------------------------------------------------------+--+ |
| | | |
| | Telemetry Events | JSON-RPC 2.0 (stdio) |
| v v |
| +--------------------------+ +-----------------------------------+ |
| | Structured JSON Logger | | FASTMCP TOOL SERVER | |
| | - RFC 3339 Timestamps | | | |
| | - Latency & Token Counts | | - Resource: schema://main | |
| | - Shadow Cost Engine | | - Tool 1: SQLite Read-Only Tool | |
| +--------------------------+ | - Tool 2: Docker Python Sandbox | |
| | - Tool 3: Resilient Web Search | |
| +-----------------------------------+ |
| | |
| +----------------------+-----------------------+ |
| | | | |
| v v v |
| +----------------+ +------------------+ +------------------+ |
| | SQLite Engine | | Docker Socket | | Search Cascade | |
| | - file:..ro | | - python:3.11 | | 1. DuckDuckGo | |
| | - SELECT only | | - --network none | | 2. Tavily API | |
| | - Zero writes | | - 256MB RAM limit| | 3. Brave Search | |
| +----------------+ +------------------+ +------------------+ |
+---------------------------------------------------------------------------------------------------+

---

## 2. Hardware Allocation & Memory Budget

[Certain] Configured to run on an **NVIDIA GeForce RTX 4060 Laptop GPU (8,192 MB GDDR6 physical VRAM)**. To avoid memory offloading to system RAM and maintain token throughput, VRAM is partitioned according to this verified allocation ledger:

+---------------------------------------------------------------------------------------------------+
| RTX 4060 LAPTOP VRAM ALLOCATION BUDGET (8,192 MB) |
+---------------------------------------------------------------------------------------------------+
| Component | Allocation Type | Memory Footprint | Headroom Status |
+-------------------------------------------+------------------+------------------+-----------------+
| Host Display Server & OS Desktop GUI | Static System | ~ 800 MB | Dedicated |
| CUDA Runtime & cuBLAS Driver Buffers | Static System | ~ 500 MB | Dedicated |
| Qwen 2.5 7B Instruct (Q4_K_M via Ollama) | Static Model | ~ 4,400 MB | Dedicated |
| nomic-embed-text-v1.5 (Q4_K via Ollama) | Static Model | ~ 280 MB | Dedicated |
| Key-Value (KV) Cache (8,192 Tokens Context| Dynamic Runtime | ~ 1,200 MB | Variable) |
+-------------------------------------------+------------------+------------------+-----------------+
| TOTAL RESERVED RUNTIME MEMORY | Active System | ~ 7,180 MB | PASS |
| UNALLOCATED SAFETY HEADROOM | Crash Buffer | ~ 1,012 MB | SAFE MARGIN |
+-------------------------------------------+------------------+------------------+-----------------+

---

## 3. Key Technical Capabilities & Production Patterns

1.  **State Machine Orchestration (LangGraph):** [Certain] Replaces fragile while-loops with an explicit Finite State Machine. Execution nodes, conditional error routing, and checkpoints are managed deterministically.
2.  **MCP Standard Compliance (FastMCP):** [Certain] Standardizes tool discovery and execution over JSON-RPC 2.0 stdio, decoupling the agent host from tool execution and eliminating framework lock-in.
3.  **Ephemeral Container Isolation (Docker Engine API):** [Certain] Executes model-generated Python code inside an ephemeral container (`python:3.11-slim`) configured with `--network none`, `--memory 256m`, a 1.0 CPU quota, a read-only root filesystem, and a 5-second wall-clock termination kill-switch.
4.  **SHA-256 Tool-Call Deduplication & Circuit Breaker:** [Certain] Computes a deterministic hash of canonicalized, key-sorted tool arguments:
    $$\text{Hash} = \text{SHA256}(\text{tool\_name} + \text{":""} + \text{sorted\_json\_string}(\text{args}))$$
    If an identical hash appears 3 times in the execution history, execution is intercepted, the tool call is bypassed, and a circuit-breaker message forces an alternate reasoning path.
5.  **Chain-of-Responsibility Search Cascade:** [Certain] Eliminates Single Sources of Failure (SSOF) and CI rate limits by cascading requests: `DuckDuckGo` (zero-key) $\rightarrow$ `Tavily Search API` $\rightarrow$ `Brave Search API`. Results are normalized into a shared Pydantic data model (`UnifiedSearchResponse`).
6.  **Dual-Metric Structured Telemetry:** [Certain] Emits RFC 3339 JSON logs directly to `stdout`. Tracks physical performance (latency, tokens/second) alongside a simulated commercial API shadow cost ($0.15 / 1M prompt tokens, $0.60 / 1M completion tokens).

---

## 4. Prerequisites & Environment Setup

### System Prerequisites
*   **Operating System:** Linux (Ubuntu 22.04+), macOS (Apple Silicon), or Windows 11 with WSL2.
*   **Container Engine:** Docker Engine or Docker Desktop with active socket access (`/var/run/docker.sock`).
*   **Inference Engine:** Ollama installed and running on `http://localhost:11434`.
*   **Python:** Python 3.11 or higher.

### 1. Pull Model Artifacts
Ensure Ollama is running and cache the required weights:
```bash
ollama pull qwen2.5:7b-instruct-q4_K_M
ollama pull nomic-embed-text:v1.5
```
### 2. Verify Docker Socket Permissions
Verify that your active user can run containers without sudo:
```bash
docker run --rm --network none python:3.11-slim python -c "print('Docker Sandbox Accessible')"
```
Note for Linux users: If permissions fail, run sudo usermod -aG docker $USER and open a new terminal session.
### 3. Clone Repository & Setup Virtual Environment
```bash
git clone https://github.com/your-username/mcp-agent-system.git
cd mcp-agent-system

python3.11 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```
### 4. Configure Environment Variables (Optional Fallbacks)
Create a .env file in the project root to configure optional search and model fallbacks:
```bash
# Optional API Search Fallbacks (Used if DuckDuckGo triggers HTTP 429 rate limits)
TAVILY_API_KEY=tvly-your-api-key-here
BRAVE_API_KEY=your-brave-key-here

# Optional Cloud Model Fallback (Used during CI runs when no GPU is present)
OPENAI_API_KEY=sk-your-openai-key-here
```

## 5. Quickstart & Usage Guide
### 1. Interactive CLI Execution
Run the agent in interactive mode with real-time streaming output:
```bash
python main.py
```
### 2. Automated Single-Query Execution with Telemetry
Execute a query directly and pipe structured telemetry logs to a file:
```bash
python main.py \
  --query "Query product_revenue for CloudEngine, calculate a 15% increase next quarter via Python, and explain the growth drivers." \
  --verbose > output.txt 2> telemetry.json
```
### 3. Verify Hardware Baseline
Run the hardware validation script to verify available GPU VRAM before execution:
```bash
python scripts/check_env.py
```

## 6. Telemetry & Observability Output Sample
[Certain] Every state transition, LLM invocation, and tool call emits an un-nested, structured JSON line to sys.stdout. Below is a production trace captured during a multi-tool execution:
```json
{
  "timestamp": "2026-10-07T04:42:15Z",
  "session_id": "c7a82b9e-6481-42e1-a08b-91f6bc3e2114",
  "event_type": "llm_completion",
  "node": "agent",
  "metrics": {
    "latency_ms": 1142.30,
    "input_tokens": 582,
    "output_tokens": 94,
    "tokens_per_second": 82.29,
    "shadow_cost_usd": 0.0001437
  },
  "payload": {
    "model": "qwen2.5:7b-instruct-q4_K_M",
    "tool_calls_requested": ["query_database"],
    "finish_reason": "tool_calls"
  }
}
```
And the subsequent containerized execution trace:
```json
{
  "timestamp": "2026-10-07T04:42:16Z",
  "session_id": "c7a82b9e-6481-42e1-a08b-91f6bc3e2114",
  "event_type": "tool_executed",
  "node": "tools",
  "metrics": {
    "latency_ms": 482.10,
    "input_tokens": 0,
    "output_tokens": 0,
    "shadow_cost_usd": 0.0
  },
  "payload": {
    "tool_name": "run_python",
    "isolation_type": "docker_container",
    "exit_code": 0,
    "fingerprint_sha256": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a"
  }
}
```

## 7. Verification & Automated Test Suite
[Certain] The test suite validates deterministic constraints, security boundaries, and protocol compliance across all three layers of the test pyramid:
```bash
# 1. Run complete unit test suite (Mocks external APIs, runs in < 2 seconds)
pytest tests/unit/ -v

# 2. Run security and containment tests (Validates Docker sandbox & SQL guardrails)
pytest tests/unit/test_sandbox_security.py tests/unit/test_sql_guardrails.py -v

# 3. Run End-to-End User Story tests (Validates US-01, US-02, and US-03 against active runner)
pytest tests/e2e/ -v
```

## 8. Technical Documentation & Architecture Records
For deeper architectural details, design trade-offs, and security boundaries, refer to the project documentation:
Product Requirement Document (PRD): Complete functional specification, user stories, acceptance criteria, and KPI definitions.
Architectural Decision Records (ADRs): Exhaustive technical justifications for all 9 architectural decisions made over naive alternatives.
Implementation Roadmap (TODO.md): Gated 5-phase engineering roadmap and task verification checklist.
Security Policy & Threat Model (SECURITY.md): Formal Trust Zone delineations, containment boundaries, and vulnerability disclosure SLAs.

## 9. Resume & Portfolio Bullet Point
This project earns the following verified line item for Forward Deployed Engineer (FDE) and AI Platform Engineering resumes:
```
"Architected a deterministic tool-calling agent using LangGraph and Model Context Protocol (FastMCP) over JSON-RPC 2.0 stdio. Implemented isolated code execution via ephemeral Docker daemon socket containers (--network none, 256MB RAM cap), SHA-256 tool-call loop mitigation, and engine-level read-only SQLite resources. Built dual-metric structured telemetry tracking latency, token throughput, and shadow cloud costs, verified by unit and end-to-end integration test suites in CI."
```