"""
Live Verification & Benchmarking Suite for Phase 1 Primitives
Tests:
  1. SQLite URI Read-Only C-level Enforcement (Isolated from authorizer)
  2. Docker Sandbox Benchmark (Latency & Timeout SLA)
  3. Live Multi-Provider Search Hierarchy (DDG, Tavily, Brave)
  4. Pydantic Output Schema Strict Validation
"""

import os
import sqlite3
import statistics
import sys
from typing import List

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.sandbox.docker_runner import DockerPythonSandbox
from src.tools.database import DatabaseEngine
from src.tools.search import ResilientSearchEngine, SearchResultItem, UnifiedSearchResponse


def log(msg: str) -> None:
    sys.stderr.write(f"\033[1;34m[CHECK]\033[0m {msg}\n")
    sys.stderr.flush()


def fail(msg: str) -> None:
    sys.stderr.write(f"\033[1;31m[FAIL]\033[0m {msg}\n")
    sys.stderr.flush()
    sys.exit(1)


def success(msg: str) -> None:
    sys.stderr.write(f"\033[1;32m[PASS]\033[0m {msg}\n")
    sys.stderr.flush()


# ============================================================================
# 1. VERIFY SQLITE URI READ-ONLY MODE (OS & C-ENGINE LEVEL)
# ============================================================================

def verify_sqlite_uri_readonly() -> None:
    log("Verifying SQLite URI read-only enforcement independent of authorizer...")
    db_path = "company_metrics.db"

    # Initialize DB file if missing
    engine = DatabaseEngine(db_path=db_path)
    abs_path = os.path.abspath(db_path)
    uri = f"file:{abs_path}?mode=ro"

    # Open raw connection using URI mode WITHOUT registering our Python authorizer callback
    conn = sqlite3.connect(uri, uri=True)
    cursor = conn.cursor()

    # Verify reads work
    cursor.execute("SELECT COUNT(*) FROM product_revenue;")
    count = cursor.fetchone()[0]
    if count == 0:
        fail("SQLite database contains zero records.")

    # Attempt write directly against SQLite C-engine
    try:
        cursor.execute("INSERT INTO product_revenue (product_name, quarter, revenue) VALUES ('Breach', 'Q1', 0);")
        conn.commit()
        conn.close()
        fail("SQLite URI mode=ro failed to block physical write operation!")
    except sqlite3.OperationalError as exc:
        if "readonly" in str(exc).lower() or "read-only" in str(exc).lower():
            success(f"SQLite URI mode=ro verified: C-engine rejected mutation with '{exc}'")
        else:
            fail(f"Unexpected SQLite error: {exc}")
    finally:
        conn.close()


# ============================================================================
# 2. DOCKER BENCHMARK: 5S SLA & COLD START METRICS
# ============================================================================

def verify_docker_benchmark() -> None:
    log("Benchmarking Docker container execution lifecycle across 5 analytical runs...")
    sandbox = DockerPythonSandbox(timeout_seconds=5)

    benchmark_script = """
import math
data = [math.sqrt(i) for i in range(1_000_000)]
print(f"SUM:{sum(data):.2f}")
"""
    latencies: List[float] = []

    for i in range(1, 6):
        res = sandbox.execute_code(benchmark_script)
        if res.exit_code != 0:
            fail(f"Run {i} failed with exit code {res.exit_code}: {res.stderr}")
        if res.timed_out:
            fail(f"Run {i} timed out unexpectedly.")
        latencies.append(res.duration_ms)
        log(f"  Iteration {i}: {res.duration_ms:.2f} ms | Output: {res.stdout.strip()}")

    p50 = statistics.median(latencies)
    max_lat = max(latencies)

    log(f"Docker Performance Metrics -> P50: {p50:.2f} ms | Max: {max_lat:.2f} ms")

    # Hard SLA verification
    if max_lat >= 5000.0:
        fail(f"Docker execution breached 5000ms hard ceiling: Max was {max_lat:.2f}ms")
    success("Docker execution benchmark confirmed: All runs completed within the 5.0s SLA.")

    # Timeout verification
    log("Verifying hard wall-clock 5.0s timeout enforcement...")
    hang_script = "import time; time.sleep(10)"
    res_hang = sandbox.execute_code(hang_script)
    if not res_hang.timed_out:
        fail("Docker sandbox failed to terminate a hanging process.")
    if res_hang.exit_code != 124:
        fail(f"Expected exit code 124 for timeout, received {res_hang.exit_code}")
    success(f"Docker timeout enforcement verified: Process terminated in {res_hang.duration_ms:.2f} ms with exit code 124.")


# ============================================================================
# 3. LIVE MULTI-PROVIDER SEARCH & 4. PYDANTIC SCHEMA VALIDATION
# ============================================================================

def verify_live_search_and_schema() -> None:
    log("Verifying live search providers and strict Pydantic schema validation...")

    tavily_key = os.getenv("TAVILY_API_KEY")
    brave_key = os.getenv("BRAVE_API_KEY")

    log(f"Keys present: Tavily={'YES' if tavily_key else 'NO'} | Brave={'YES' if brave_key else 'NO'}")

    engine = ResilientSearchEngine(
        tavily_api_key=tavily_key,
        brave_api_key=brave_key,
        timeout_seconds=4.0
    )

    # Helper function to validate schema strictness
    def validate_schema(resp: UnifiedSearchResponse, expected_provider: str) -> None:
        if not isinstance(resp, UnifiedSearchResponse):
            fail(f"Search returned non-Pydantic object: {type(resp)}")

        # Validate serialization round-trip
        dumped = resp.model_dump()
        reconstructed = UnifiedSearchResponse.model_validate(dumped)

        if reconstructed.provider_used != expected_provider:
            fail(f"Provider mismatch: Expected {expected_provider}, got {reconstructed.provider_used}")

        if not reconstructed.results:
            fail(f"Provider {expected_provider} returned 0 results for live query.")

        for item in reconstructed.results:
            if not isinstance(item, SearchResultItem):
                fail(f"Result item {item} is not SearchResultItem")
            if not item.title or not item.snippet or not item.source_url:
                fail(f"Item contains empty required fields: {item}")
            if not item.source_url.startswith(("http://", "https://")):
                fail(f"URL violates schema format: {item.source_url}")

    # Level 1: Live DuckDuckGo
    log("Testing Tier 1 (DuckDuckGo Live)...")
    ddg_resp = engine._try_duckduckgo("latest Python 3.11 release", max_results=2)
    if ddg_resp is None:
        fail("DuckDuckGo failed live request (IP rate-limited or scraper blocked).")
    validate_schema(ddg_resp, "DuckDuckGo")
    success(f"Tier 1 (DuckDuckGo) verified with {len(ddg_resp.results)} schema-compliant results.")

    # Level 2: Live Tavily (if key provided)
    if tavily_key:
        log("Testing Tier 2 (Tavily Live Direct)...")
        tavily_resp = engine._try_tavily("LangGraph state machine architecture", max_results=2)
        if tavily_resp is None:
            fail("Tavily API call failed. Verify TAVILY_API_KEY validity or network access.")
        validate_schema(tavily_resp, "Tavily")
        success(f"Tier 2 (Tavily) verified with {len(tavily_resp.results)} schema-compliant results.")
    else:
        log("\033[1;33m[SKIP]\033[0m TAVILY_API_KEY not set. Skipping live authenticated Tavily test.")

    # Level 3: Live Brave (if key provided)
    if brave_key:
        log("Testing Tier 3 (Brave Live Direct)...")
        brave_resp = engine._try_brave("Docker daemon socket security", max_results=2)
        if brave_resp is None:
            fail("Brave Search API call failed. Verify BRAVE_API_KEY validity or network access.")
        validate_schema(brave_resp, "BraveSearch")
        success(f"Tier 3 (Brave) verified with {len(brave_resp.results)} schema-compliant results.")
    else:
        log("\033[1;33m[SKIP]\033[0m BRAVE_API_KEY not set. Skipping live authenticated Brave test.")

    # Cascade Test: Simulate DuckDuckGo failure to confirm fallback to Tavily
    if tavily_key:
        log("Simulating DuckDuckGo failure to verify automated cascade to Tavily...")
        engine_broken_ddg = ResilientSearchEngine(tavily_api_key=tavily_key, brave_api_key=brave_key)
        # Monkeypatch internal DDG method to simulate rate limit
        engine_broken_ddg._try_duckduckgo = lambda q, m: None
        cascade_resp = engine_broken_ddg.search("test query", max_results=1)
        validate_schema(cascade_resp, "Tavily")
        success("Automated cascade from failed DDG to live Tavily verified.")


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    sys.stderr.write("\n=======================================================\n")
    sys.stderr.write("   STARTING PHASE 1 LIVE VERIFICATION & BENCHMARKING    \n")
    sys.stderr.write("=======================================================\n\n")

    verify_sqlite_uri_readonly()
    sys.stderr.write("\n" + "-" * 55 + "\n\n")

    verify_docker_benchmark()
    sys.stderr.write("\n" + "-" * 55 + "\n\n")

    verify_live_search_and_schema()
    sys.stderr.write("\n=======================================================\n")
    sys.stderr.write("     ALL LIVE PHASE 1 CHECKS SUCCESSFULLY VERIFIED      \n")
    sys.stderr.write("=======================================================\n\n")
