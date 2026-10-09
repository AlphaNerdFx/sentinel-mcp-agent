import pytest
from src.tools.database import DatabaseEngine, SecurityViolationError
from src.sandbox.docker_runner import DockerPythonSandbox
from src.telemetry.cost import ShadowCostCalculator

# Test 1: SQLite Security Authorization Boundary
def test_sql_engine_prevents_destructive_operations(tmp_path):
    db_file = str(tmp_path / "test_metrics.db")
    engine = DatabaseEngine(db_path=db_file)
    
    # Verify standard read succeeds
    rows = engine.execute_query("SELECT revenue FROM product_revenue WHERE product_name = 'CloudEngine';")
    assert len(rows) == 2
    assert rows[0]["revenue"] == 1250000.00
    
    # Verify mutation is blocked by SQLite Authorizer
    with pytest.raises(SecurityViolationError) as exc_info:
        engine.execute_query("DROP TABLE product_revenue;")
    assert "Security Policy Violation" in str(exc_info.value)

    # Verify obfuscated comment attacks are blocked
    with pytest.raises(SecurityViolationError):
        engine.execute_query("DELETE/**/FROM product_revenue;")

# Test 2: Docker Sandbox Security & Constraints
def test_sandbox_network_isolation():
    sandbox = DockerPythonSandbox()
    # Attempt an outbound network connection
    network_bomb = (
        "import urllib.request; "
        "urllib.request.urlopen('http://1.1.1.1', timeout=1)"
    )
    result = sandbox.execute_code(network_bomb)
    assert result.exit_code != 0
    # Must fail with network unreachable / resolution error
    assert "Network is unreachable" in result.stderr or "URLError" in result.stderr

def test_sandbox_wall_clock_timeout():
    sandbox = DockerPythonSandbox(timeout_seconds=2)
    hang_code = "import time; time.sleep(10)"
    result = sandbox.execute_code(hang_code)
    assert result.timed_out is True
    assert result.exit_code == 124

# Test 3: Shadow Cost Mathematical Precision
def test_cost_calculation():
    # 10,000 input tokens ($0.0015) + 2,000 output tokens ($0.0012) = $0.0027
    cost = ShadowCostCalculator.calculate_cost(input_tokens=10_000, output_tokens=2_000)
    assert cost == 0.0027