# File: tests/unit/test_search.py
import pytest
from unittest.mock import patch, MagicMock
import urllib.error
from src.tools.search import ResilientSearchEngine

def test_tier1_duckduckgo_success():
    """Verify DuckDuckGo succeeds without evaluating downstream fallback keys."""
    engine = ResilientSearchEngine()
    
    mock_ddg_results = [{"title": "Python 3.11", "body": "Fast runtime", "href": "https://python.org"}]
    
    with patch("duckduckgo_search.DDGS") as mock_ddg:
        instance = mock_ddg.return_value.__enter__.return_value
        instance.text.return_value = iter(mock_ddg_results)
        
        response = engine.search("python programming", max_results=1)
        assert response.provider_used == "DuckDuckGo"
        assert len(response.results) == 1
        assert response.results[0].title == "Python 3.11"
        assert response.results[0].source_url == "https://python.org"

def test_tier1_failure_cascades_to_tier2_tavily():
    """Verify HTTP 429 on DuckDuckGo triggers an immediate fallback to Tavily."""
    engine = ResilientSearchEngine(tavily_api_key="tvly-mock-key")
    
    # Mock DDGS raising an exception
    with patch("duckduckgo_search.DDGS", side_effect=Exception("HTTP 429 Rate Limit")):
        # Mock Tavily REST API returning HTTP 200
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b'{"results": [{"title": "Tavily Match", "content": "Clean snippet", "url": "https://tavily.com"}]}'
        mock_response.__enter__.return_value = mock_response
        
        with patch("urllib.request.urlopen", return_value=mock_response):
            response = engine.search("market projection", max_results=1)
            assert response.provider_used == "Tavily"
            assert response.results[0].title == "Tavily Match"
            assert response.results[0].source_url == "https://tavily.com"

def test_all_tiers_failing_returns_exhausted_gracefully():
    """Verify complete failure across all tiers returns an Exhausted payload rather than crashing."""
    engine = ResilientSearchEngine(tavily_api_key="mock", brave_api_key="mock")
    
    with patch("duckduckgo_search.DDGS", side_effect=Exception("DDG Blocked")):
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Network Unreachable")):
            response = engine.search("impossible query")
            assert response.provider_used == "Exhausted"
            assert response.results == []
            assert "No external search results found" in response.to_context_string()