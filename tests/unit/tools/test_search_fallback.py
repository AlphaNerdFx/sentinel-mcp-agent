"""
tests/unit/tools/test_search_fallback.py
Verifies Chain-of-Responsibility fallback cascade across search providers.
Contract Reference: SPEC_V1.md COMP-07; PRD_V1.md ADR-07.
"""

from unittest.mock import patch

import pytest

from src.tools.search import (
    ResilientSearchEngine,
    SearchResultItem,
    UnifiedSearchResponse,
)


@pytest.fixture
def mock_results():
    """[Certain] Standard canned search items."""
    return [
        SearchResultItem(
            title="Q3 Cloud Metrics",
            snippet="CloudEngine generated $125k in Q2 revenue.",
            source_url="https://metrics.internal/q2",
        )
    ]


class TestSearchFallbackCascade:
    def test_tier1_duckduckgo_success(self, mock_results):
        """[Certain] Primary provider succeeds; secondary providers are not invoked."""
        engine = ResilientSearchEngine(tavily_api_key="tvly-mock", brave_api_key="brave-mock")

        with (
            patch.object(engine, "_duckduckgo_search", return_value=mock_results) as mock_ddg,
            patch.object(engine, "_tavily_search") as mock_tavily,
            patch.object(engine, "_brave_search") as mock_brave,
        ):
            response: UnifiedSearchResponse = engine.search("CloudEngine revenue", max_results=1)

            assert response.provider_used == "DuckDuckGo"
            assert len(response.results) == 1
            assert response.results[0].title == "Q3 Cloud Metrics"
            mock_ddg.assert_called_once()
            mock_tavily.assert_not_called()
            mock_brave.assert_not_called()

    def test_tier2_fallback_to_tavily_on_duckduckgo_failure(self, mock_results):
        """[Certain] DuckDuckGo encounters rate limit; execution falls back to Tavily."""
        engine = ResilientSearchEngine(tavily_api_key="tvly-mock", brave_api_key="brave-mock")

        with (
            patch.object(engine, "_duckduckgo_search", side_effect=RuntimeError("HTTP 429")),
            patch.object(engine, "_tavily_search", return_value=mock_results) as mock_tavily,
            patch.object(engine, "_brave_search") as mock_brave,
        ):
            response: UnifiedSearchResponse = engine.search("CloudEngine revenue")

            assert response.provider_used == "Tavily"
            assert len(response.results) == 1
            mock_tavily.assert_called_once()
            mock_brave.assert_not_called()

    def test_tier3_fallback_to_brave_on_tavily_failure(self, mock_results):
        """[Certain] DuckDuckGo and Tavily fail; execution cascades to Brave Search."""
        engine = ResilientSearchEngine(tavily_api_key="tvly-mock", brave_api_key="brave-mock")

        with (
            patch.object(engine, "_duckduckgo_search", side_effect=RuntimeError("Timeout")),
            patch.object(engine, "_tavily_search", side_effect=Exception("Quota Exceeded")),
            patch.object(engine, "_brave_search", return_value=mock_results) as mock_brave,
        ):
            response: UnifiedSearchResponse = engine.search("CloudEngine revenue")

            assert response.provider_used == "BraveSearch"
            assert len(response.results) == 1
            mock_brave.assert_called_once()

    def test_total_exhaustion_returns_clean_response(self):
        """
        [Certain] Verifies Invariant 2: when all providers fail, returns
        provider_used='Exhausted' with results=[] without raising unhandled exceptions.
        """
        engine = ResilientSearchEngine(tavily_api_key="tvly-mock", brave_api_key="brave-mock")

        with (
            patch.object(engine, "_duckduckgo_search", side_effect=RuntimeError("DDG Down")),
            patch.object(engine, "_tavily_search", side_effect=RuntimeError("Tavily Down")),
            patch.object(engine, "_brave_search", side_effect=RuntimeError("Brave Down")),
        ):
            response: UnifiedSearchResponse = engine.search("CloudEngine revenue")

            assert response.provider_used == "Exhausted"
            assert response.results == []
            assert "No search results available" in response.to_context_string()

    def test_unconfigured_api_keys_are_bypassed(self):
        """[Certain] Providers lacking credentials must be bypassed in the cascade."""
        engine = ResilientSearchEngine(tavily_api_key=None, brave_api_key=None)

        with (
            patch.object(engine, "_duckduckgo_search", side_effect=Exception("DDG Down")),
            patch.object(engine, "_tavily_search") as mock_tavily,
            patch.object(engine, "_brave_search") as mock_brave,
        ):
            response = engine.search("Test query")

            assert response.provider_used == "Exhausted"
            mock_tavily.assert_not_called()
            mock_brave.assert_not_called()
