import json
from unittest.mock import patch

import pytest

from src.sandbox.docker_runner import ExecutionResult
from src.server import get_db_schema, query_database, run_python, web_search
from src.tools.search import SearchResultItem, UnifiedSearchResponse


@pytest.mark.asyncio
async def test_mcp_server_resource_registry():
    """Verify schema://main resource returns table DDL."""
    schema = get_db_schema()
    assert "CREATE TABLE product_revenue" in schema


@pytest.mark.asyncio
async def test_mcp_query_database_success():
    """Verify query_database tool formats records into a valid JSON string."""
    result = query_database("SELECT product_name, revenue FROM product_revenue LIMIT 1;")
    data = json.loads(result)
    assert isinstance(data, list)
    assert len(data) == 1
    assert "revenue" in data[0]


@pytest.mark.asyncio
async def test_mcp_query_database_security_violation():
    """Verify security violations return an explicit policy string rather than crashing."""
    result = query_database("DROP TABLE product_revenue;")
    assert "Security Violation" in result


@pytest.mark.asyncio
async def test_mcp_run_python_success():
    """Verify run_python forwards output cleanly."""
    mock_res = ExecutionResult(
        stdout="Calculated: 42\n", stderr="", exit_code=0, duration_ms=45.0, timed_out=False
    )
    with patch("src.server.sandbox.execute_code", return_value=mock_res):
        output = run_python("print('Calculated: 42')")
        assert output == "Calculated: 42"


@pytest.mark.asyncio
async def test_mcp_run_python_timeout_handling():
    """Verify timed-out executions return a POSIX kill message."""
    mock_res = ExecutionResult(
        stdout="", stderr="", exit_code=124, duration_ms=5000.0, timed_out=True
    )
    with patch("src.server.sandbox.execute_code", return_value=mock_res):
        output = run_python("while True: pass")
        assert "timed out after 5.0 seconds" in output


@pytest.mark.asyncio
async def test_mcp_web_search_forwarding():
    """Verify web_search tool normalizes search context output."""
    mock_search_res = UnifiedSearchResponse(
        provider_used="DuckDuckGo",
        query="test query",
        results=[
            SearchResultItem(
                title="Result 1", snippet="Snippet 1", source_url="https://example.com"
            )
        ],
    )
    with patch("src.server.search_engine.search", return_value=mock_search_res):
        output = web_search("test query")
        assert "Source: DuckDuckGo" in output
        assert "Result 1" in output
