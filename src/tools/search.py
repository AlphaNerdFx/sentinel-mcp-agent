"""
Resilient Multi-Provider Search Engine (COMP-07)
Implements a 3-tier Chain of Responsibility fallback hierarchy:
DuckDuckGo -> Tavily API -> Brave Search API -> Exhausted Null Object.
"""

import os
import sys
import json
import urllib.request
import urllib.parse
from typing import List, Literal, Optional
from pydantic import BaseModel, Field

class SearchResultItem(BaseModel):
    title: str = Field(..., description="The title of the search result page.")
    snippet: str = Field(..., description="Extracted contextual text snippet.")
    source_url: str = Field(..., description="Fully qualified HTTP/HTTPS URL.")

class UnifiedSearchResponse(BaseModel):
    provider_used: Literal["DuckDuckGo", "Tavily", "BraveSearch", "Exhausted"]
    query: str
    results: List[SearchResultItem] = Field(default_factory=list)

    def to_context_string(self) -> str:
        """Formats normalized results into a deterministic LLM prompt context block."""
        if self.provider_used == "Exhausted" or not self.results:
            return "No external search results found. Proceed with internal reasoning."
        
        lines = [f"### Web Search Results (Source: {self.provider_used}) for: '{self.query}'"]
        for idx, item in enumerate(self.results, start=1):
            lines.append(f"[{idx}] {item.title}\n    Snippet: {item.snippet}\n    URL: {item.source_url}")
        return "\n".join(lines)


class ResilientSearchEngine:
    def __init__(
        self,
        tavily_api_key: Optional[str] = None,
        brave_api_key: Optional[str] = None,
        timeout_seconds: float = 4.0,
    ) -> None:
        self.tavily_api_key = tavily_api_key or os.getenv("TAVILY_API_KEY")
        self.brave_api_key = brave_api_key or os.getenv("BRAVE_API_KEY")
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, max_results: int = 3) -> UnifiedSearchResponse:
        """
        Executes cascade: DuckDuckGo -> Tavily -> Brave -> Graceful Degradation.
        Guaranteed never to raise an unhandled network exception to the orchestrator.
        """
        # Tier 1: DuckDuckGo (Zero-Cost Scraped Engine)
        tier1_result = self._try_duckduckgo(query, max_results)
        if tier1_result is not None:
            return tier1_result

        # Tier 2: Tavily Search API
        tier2_result = self._try_tavily(query, max_results)
        if tier2_result is not None:
            return tier2_result

        # Tier 3: Brave Search API
        tier3_result = self._try_brave(query, max_results)
        if tier3_result is not None:
            return tier3_result

        # Graceful Terminal Fallback: Null Object Pattern
        sys.stderr.write(f"[WARN] All search tiers exhausted for query: '{query}'\n")
        sys.stderr.flush()
        return UnifiedSearchResponse(
            provider_used="Exhausted",
            query=query,
            results=[]
        )

    def _try_duckduckgo(self, query: str, max_results: int) -> Optional[UnifiedSearchResponse]:
        """Tier 1 implementation using duckduckgo_search library."""
        try:
            from duckduckgo_search import DDGS  # Lazy import to accelerate CLI boot
            results: List[SearchResultItem] = []
            with DDGS(timeout=int(self.timeout_seconds)) as ddgs:
                raw_results = list(ddgs.text(query, max_results=max_results))
                for item in raw_results:
                    results.append(SearchResultItem(
                        title=item.get("title", "Untitled"),
                        snippet=item.get("body", ""),
                        source_url=item.get("href", "")
                    ))
            if results:
                return UnifiedSearchResponse(
                    provider_used="DuckDuckGo",
                    query=query,
                    results=results
                )
        except Exception as exc:
            sys.stderr.write(f"[INFO] Tier 1 (DuckDuckGo) bypassed: {exc}\n")
            sys.stderr.flush()
        return None

    def _try_tavily(self, query: str, max_results: int) -> Optional[UnifiedSearchResponse]:
        """Tier 2 implementation using direct Tavily REST API calls."""
        if not self.tavily_api_key:
            return None

        url = "https://api.tavily.com/search"
        payload = {
            "api_key": self.tavily_api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
            "include_answer": False
        }
        
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "MCP-Agent/1.0"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    results = [
                        SearchResultItem(
                            title=item.get("title", "Untitled"),
                            snippet=item.get("content", ""),
                            source_url=item.get("url", "")
                        )
                        for item in data.get("results", [])
                    ]
                    return UnifiedSearchResponse(
                        provider_used="Tavily",
                        query=query,
                        results=results
                    )
        except Exception as exc:
            sys.stderr.write(f"[INFO] Tier 2 (Tavily) bypassed: {exc}\n")
            sys.stderr.flush()
        return None

    def _try_brave(self, query: str, max_results: int) -> Optional[UnifiedSearchResponse]:
        """Tier 3 implementation using Brave Search REST API."""
        if not self.brave_api_key:
            return None

        params = urllib.parse.urlencode({"q": query, "count": max_results})
        url = f"https://api.search.brave.com/res/v1/web/search?{params}"
        
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": self.brave_api_key,
                    "User-Agent": "MCP-Agent/1.0"
                },
                method="GET"
            )
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    web_results = data.get("web", {}).get("results", [])
                    results = [
                        SearchResultItem(
                            title=item.get("title", "Untitled"),
                            snippet=item.get("description", ""),
                            source_url=item.get("url", "")
                        )
                        for item in web_results
                    ]
                    return UnifiedSearchResponse(
                        provider_used="BraveSearch",
                        query=query,
                        results=results
                    )
        except Exception as exc:
            sys.stderr.write(f"[INFO] Tier 3 (Brave) bypassed: {exc}\n")
            sys.stderr.flush()
        return None