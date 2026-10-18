"""
src/agent/model_adapter.py
Model Provider Adapter Factory supporting Local Ollama and Cloud Fallbacks.
Contract Reference: SPEC_V1.md COMP-02; PRD_V1.md Section 5.1, ADR-04, ADR-10.
"""

from __future__ import annotations

import os
import urllib.request
from collections.abc import Sequence
from typing import Any, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from pydantic import SecretStr


def is_ollama_online(base_url: str = "http://localhost:11434") -> bool:
    """[Certain] Probes Ollama version endpoint with a 2.0s deadline."""
    try:
        req = urllib.request.Request(f"{base_url}/api/version")
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return bool(resp.status == 200)
    except Exception:
        return False


def get_model(
    tools: Optional[Sequence[BaseTool]] = None,
    temperature: float = 0.0,
    local_model: str = "qwen2.5:7b-instruct-q4_K_M",
    cloud_fallback_model: str = "gpt-4o-mini",
) -> BaseChatModel | Runnable[Any, Any]:
    """[Certain] Factory instantiating deterministic ChatOpenAI client."""
    timeout_val = float(os.getenv("MODEL_TIMEOUT", "120.0"))

    if os.getenv("SENTINEL_MOCK_MODEL") == "1":
        from langchain_community.chat_models import FakeListChatModel
        # Returns instant deterministic tool calls for automated test suites
        return FakeListChatModel(
            responses=[
                '{"name": "query_database", "arguments": {"query": "SELECT revenue FROM product_revenue WHERE product_name=\'CloudEngine\' AND quarter=\'Q1\'"}}',
                "3450000",
            ]
        )

    if is_ollama_online():
        model = ChatOpenAI(
            model=local_model,
            base_url="http://localhost:11434/v1",
            api_key=SecretStr("ollama"),
            temperature=temperature,
            timeout=timeout_val,
            extra_body={"keep_alive": -1},
        )
    else:
        openai_key = os.getenv("OPENAI_API_KEY", "mock_key")
        model = ChatOpenAI(
            model=cloud_fallback_model,
            api_key=SecretStr(openai_key),
            temperature=temperature,
            timeout=timeout_val,
        )

    if tools:
        return model.bind_tools(tools)
    return model
