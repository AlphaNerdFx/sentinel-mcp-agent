from src.agent.circuit_breaker import ToolCallCircuitBreaker

def test_ast_normalization_catches_syntactic_variance():
    """Verify SQL syntax formatting variations resolve to identical signatures."""
    query_a = "SELECT product_name, revenue FROM product_revenue WHERE quarter = 'Q1-2026';"
    query_b = "select   product_name,   revenue   from product_revenue  where  quarter='Q1-2026' ;"

    hash_a = ToolCallCircuitBreaker.compute_fingerprint("query_database", {"sql_query": query_a})
    hash_b = ToolCallCircuitBreaker.compute_fingerprint("query_database", {"sql_query": query_b})

    assert hash_a == hash_b, "AST normalization failed to detect identical SQL semantics"

def test_strike_counter_and_circuit_tripping():
    """Verify identical tool executions trip the circuit breaker on Strike 3."""
    history = []
    tool_name = "query_database"
    args = {"sql_query": "SELECT * FROM product_revenue;"}
    
    fp = ToolCallCircuitBreaker.compute_fingerprint(tool_name, args)
    
    # Strike 1
    tripped, count = ToolCallCircuitBreaker.inspect_call(fp, history)
    assert not tripped
    assert count == 1
    history.append(fp)
    
    # Strike 2
    tripped, count = ToolCallCircuitBreaker.inspect_call(fp, history)
    assert not tripped
    assert count == 2
    history.append(fp)
    
    # Strike 3: Circuit Tripped
    tripped, count = ToolCallCircuitBreaker.inspect_call(fp, history)
    assert tripped
    assert count == 3