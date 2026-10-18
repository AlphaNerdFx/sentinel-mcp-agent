"""
src/tools/search.py
Multi-Provider Resilient Search Engine with Chain-of-Responsibility Cascade.
Contract Reference: SPEC_V1.md COMP-07; PRD_V1.md ADR-07.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class SearchResultItem(BaseModel):
    title: str = Field(description="Title of search result")
    snippet: str = Field(description="Text excerpt or content summary")
    source_url: str = Field(description="Direct URL to source")


class UnifiedSearchResponse(BaseModel):
    provider_used: Literal["DuckDuckGo", "Tavily", "BraveSearch", "Exhausted"]
    query: str
    results: List[SearchResultItem] = Field(default_factory=list)

    def to_context_string(self) -> str:
        if self.provider_used == "Exhausted" or not self.results:
            return "No search results available. Proceed with internal reasoning."
        lines = [f"### Web Search Results (Source: {self.provider_used}) for: '{self.query}'"]
        for idx, item in enumerate(self.results, start=1):
            lines.append(f"{idx}. [{item.title}]({item.source_url})\n   {item.snippet}")
        return "\n".join(lines)


class ResilientSearchEngine:
    """
    [Certain] Chain-of-Responsibility Search Engine.
    Cascade: DuckDuckGo -> Tavily -> Brave Search -> Exhausted.
    """

    def __init__(
        self,
        tavily_api_key: Optional[str] = None,
        brave_api_key: Optional[str] = None,
        timeout_seconds: float = 4.0,
    ) -> None:
        self.tavily_api_key = tavily_api_key or os.getenv("TAVILY_API_KEY")
        self.brave_api_key = brave_api_key or os.getenv("BRAVE_API_KEY")
        self.timeout_seconds = timeout_seconds

    def _duckduckgo_search(self, query: str, max_results: int) -> List[SearchResultItem]:
        """[Certain] Executes DuckDuckGo search with recent time-window fallback."""
        from ddgs import DDGS

        with DDGS(timeout=int(self.timeout_seconds)) as ddgs:
            # Query past month for temporal freshness
            raw_results = list(ddgs.text(query, max_results=max_results, timelimit="m"))

            # Fall back to unbounded search if temporal filter yields 0 results
            if not raw_results:
                raw_results = list(ddgs.text(query, max_results=max_results))

            items: List[SearchResultItem] = []
            for r in raw_results:
                items.append(
                    SearchResultItem(
                        title=r.get("title", ""),
                        snippet=r.get("body", ""),
                        source_url=r.get("href", ""),
                    )
                )
            return items

    def _tavily_search(self, query: str, max_results: int) -> List[SearchResultItem]:
        """Tier 2: Tavily Paid Commercial Search API."""
        if not self.tavily_api_key:
            raise ValueError("Tavily API key unconfigured")

        url = "https://api.tavily.com/search"
        payload = {
            "api_key": self.tavily_api_key,
            "query": query,
            "max_results": max_results,
            "include_answer": False,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
            raw = json.loads(resp.read().decode("utf-8"))

        results: List[SearchResultItem] = []
        for r in raw.get("results", []):
            results.append(
                SearchResultItem(
                    title=r.get("title", ""),
                    snippet=r.get("content", ""),
                    source_url=r.get("url", ""),
                )
            )
        if not results:
            raise RuntimeError("Tavily returned zero results")
        return results

    def _brave_search(self, query: str, max_results: int) -> List[SearchResultItem]:
        """Tier 3: Brave Commercial Search API."""
        if not self.brave_api_key:
            raise ValueError("Brave API key unconfigured")

        params = urllib.parse.urlencode({"q": query, "count": max_results})
        url = f"https://api.search.brave.com/res/v1/web/search?{params}"
        req = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "X-Subscription-Token": self.brave_api_key},
        )
        with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
            raw = json.loads(resp.read().decode("utf-8"))

        results: List[SearchResultItem] = []
        for r in raw.get("web", {}).get("results", []):
            results.append(
                SearchResultItem(
                    title=r.get("title", ""),
                    snippet=r.get("description", ""),
                    source_url=r.get("url", ""),
                )
            )
        if not results:
            raise RuntimeError("Brave returned zero results")
        return results

    def search(self, query: str, max_results: int = 3) -> UnifiedSearchResponse:
        """[Certain] Executes sequential fallback across providers."""
        # Tier 1: DuckDuckGo
        try:
            ddg_res = self._duckduckgo_search(query, max_results)
            return UnifiedSearchResponse(provider_used="DuckDuckGo", query=query, results=ddg_res)
        except Exception as exc:
            sys.stderr.write(f"[INFO] Tier 1 (DuckDuckGo) bypassed: {exc}\n")

        # Tier 2: Tavily
        if self.tavily_api_key:
            try:
                tavily_res = self._tavily_search(query, max_results)
                return UnifiedSearchResponse(
                    provider_used="Tavily", query=query, results=tavily_res
                )
            except Exception as exc:
                sys.stderr.write(f"[INFO] Tier 2 (Tavily) bypassed: {exc}\n")

        # Tier 3: Brave
        if self.brave_api_key:
            try:
                brave_res = self._brave_search(query, max_results)
                return UnifiedSearchResponse(
                    provider_used="BraveSearch", query=query, results=brave_res
                )
            except Exception as exc:
                sys.stderr.write(f"[INFO] Tier 3 (Brave) bypassed: {exc}\n")

        # Total Exhaustion
        return UnifiedSearchResponse(provider_used="Exhausted", query=query, results=[])
