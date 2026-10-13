"""src/agent/model_adapter.py
Provider Model Factory with Robust Transport Deadlines & Schema Binding.
"""
from __future__ import annotations

import os
import urllib.request
from typing import List, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI


def is_ollama_online(base_url: str = "http://localhost:11434") -> bool:
    """Verifies that the Ollama HTTP daemon is responding."""
    try:
        req = urllib.request.Request(f"{base_url}/api/version", method="GET")
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return resp.status == 200
    except Exception:
        return False


def get_model(
    tools: Optional[List[BaseTool]] = None,
    temperature: float = 0.0,
    local_model: str = "qwen2.5:7b-instruct-q4_K_M",
    cloud_fallback_model: str = "gpt-4o-mini",
) -> BaseChatModel:
    """Builds a ChatOpenAI model bound to local Ollama or cloud fallback."""
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    # Transport timeout: Give local GPU sufficient headroom for schema evaluation
    timeout = float(os.getenv("MODEL_TIMEOUT", "120.0"))

    if is_ollama_online(ollama_url):
        model = ChatOpenAI(
            base_url=f"{ollama_url}/v1",
            api_key="ollama",
            model=local_model,
            temperature=temperature,
            timeout=timeout,
            max_retries=1,
        )
    else:
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key and not openai_key.startswith("mock_"):
            model = ChatOpenAI(
                api_key=openai_key,
                model=cloud_fallback_model,
                temperature=temperature,
                timeout=timeout,
                max_retries=2,
            )
        else:
            raise ConnectionError(
                f"Model provider unreachable: Local Ollama offline at {ollama_url} "
                "and no valid OPENAI_API_KEY found for cloud fallback."
            )

    if tools:
        return model.bind_tools(tools)
    return model