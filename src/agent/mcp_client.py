"""src/agent/mcp_client.py
Native FastMCP Client Manager with LangChain Tool Adapter.
"""
from __future__ import annotations

import sys
from typing import Any, Dict, List
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from langchain_core.tools import StructuredTool
from pydantic import create_model


class MCPClientManager:
    """Manages an out-of-process FastMCP server over stdio via native fastmcp.Client."""

    def __init__(self, server_script: str = "src/server.py") -> None:
        self.server_script = server_script
        self.transport = StdioTransport(
            command=sys.executable,
            args=[self.server_script],
        )
        self.client = Client(self.transport)
        self._tools: List[StructuredTool] = []
        self._is_connected = False

    async def initialize(self) -> List[StructuredTool]:
        """Establishes connection to the MCP server and adapts discovered tools."""
        if not self._is_connected:
            await self.client.__aenter__()
            self._is_connected = True

        mcp_tools = await self.client.list_tools()
        self._tools = []

        for tool_def in mcp_tools:
            name = tool_def.name
            description = tool_def.description or ""
            input_schema = tool_def.input_schema or {}

            def make_coro(tool_name: str):
                async def _coro(**kwargs: Any) -> Any:
                    result = await self.client.call_tool(tool_name, kwargs)
                    if hasattr(result, "data") and result.data is not None:
                        return result.data
                    if hasattr(result, "content") and result.content:
                        return "\n".join(c.text for c in result.content if hasattr(c, "text"))
                    return str(result)
                return _coro

            fields: Dict[str, Any] = {}
            properties = input_schema.get("properties", {})
            required = input_schema.get("required", [])

            for prop_name, prop_meta in properties.items():
                py_type = str
                if prop_meta.get("type") == "integer":
                    py_type = int
                elif prop_meta.get("type") == "number":
                    py_type = float
                elif prop_meta.get("type") == "boolean":
                    py_type = bool

                if prop_name in required:
                    fields[prop_name] = (py_type, ...)
                else:
                    fields[prop_name] = (py_type, None)

            schema_model = create_model(f"{name}_schema", **fields)

            self._tools.append(
                StructuredTool(
                    name=name,
                    description=description,
                    args_schema=schema_model,
                    coroutine=make_coro(name),
                )
            )

        return self._tools

    @property
    def tools(self) -> List[StructuredTool]:
        if not self._tools:
            raise RuntimeError("MCPClientManager uninitialized. Call initialize() first.")
        return self._tools

    def get_tool_by_name(self, name: str) -> StructuredTool:
        for tool in self.tools:
            if tool.name == name:
                return tool
        raise KeyError(f"Tool '{name}' not found in active MCP tool registry.")

    async def close(self) -> None:
        """Closes the client session and joins child worker pipes."""
        if self._is_connected:
            await self.client.__aexit__(None, None, None)
            self._is_connected = False