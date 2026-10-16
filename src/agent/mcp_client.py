"""Native FastMCP client manager with LangChain tool adapter."""

from __future__ import annotations

import sys
from typing import Any, Optional

from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, create_model


class MCPClientManager:
    """Manage an out-of-process FastMCP server over stdio."""

    def __init__(self, server_script: str = "src/server.py") -> None:
        self.server_script = server_script
        self.transport = StdioTransport(
            command=sys.executable,
            args=[self.server_script],
        )
        self.client = Client(self.transport)
        self._tools: list[StructuredTool] = []
        self._is_connected = False

    async def initialize(self) -> list[StructuredTool]:
        """Connect to the MCP server and adapt its tools."""
        if not self._is_connected:
            await self.client.__aenter__()
            self._is_connected = True

        try:
            mcp_tools = await self.client.list_tools()
            tools: list[StructuredTool] = []

            for tool_def in mcp_tools:
                name = tool_def.name
                description = tool_def.description or ""
                input_schema = tool_def.input_schema or {}

                schema_model = self._create_pydantic_schema(
                    name,
                    input_schema,
                )

                async def execute(
                    tool_name: str = name,
                    **kwargs: Any,
                ) -> Any:
                    result = await self.client.call_tool(
                        tool_name,
                        kwargs,
                    )

                    if hasattr(result, "data") and result.data is not None:
                        return result.data

                    if hasattr(result, "content") and result.content:
                        return "\n".join(
                            item.text for item in result.content if hasattr(item, "text")
                        )

                    return str(result)

                tools.append(
                    StructuredTool(
                        name=name,
                        description=description,
                        args_schema=schema_model,
                        coroutine=execute,
                    )
                )

            self._tools = tools
            return self._tools

        except Exception:
            await self.close()
            raise

    def _create_pydantic_schema(
        self,
        tool_name: str,
        schema_dict: dict[str, Any],
    ) -> type[BaseModel]:
        """Build a Pydantic model from an MCP input schema."""
        properties = schema_dict.get("properties", {})
        required_fields = set(schema_dict.get("required", []))

        type_map: dict[str, type[Any]] = {
            "integer": int,
            "number": float,
            "boolean": bool,
            "string": str,
        }

        fields: dict[str, Any] = {}

        for prop_name, prop_attrs in properties.items():
            prop_type = prop_attrs.get("type", "string")
            field_type = type_map.get(prop_type, str)
            description = prop_attrs.get("description", "")

            if prop_name in required_fields:
                fields[prop_name] = (
                    field_type,
                    Field(description=description),
                )
            else:
                fields[prop_name] = (
                    Optional[field_type],
                    Field(default=None, description=description),
                )

        return create_model(f"{tool_name}_InputSchema", **fields)

    @property
    def tools(self) -> list[StructuredTool]:
        """Return discovered tools, requiring initialization first."""
        if not self._is_connected or not self._tools:
            raise RuntimeError("MCPClientManager uninitialized. Call initialize() first.")
        return self._tools

    def get_tool_by_name(self, name: str) -> StructuredTool:
        """Retrieve a registered tool by name."""
        for tool in self.tools:
            if tool.name == name:
                return tool

        raise KeyError(f"Tool '{name}' not found in active MCP tool registry.")

    async def _execute_tool(
        self,
        name: str,
        args: dict[str, Any],
    ) -> str:
        """Execute a registered MCP tool."""
        raw_result = await self.client.call_tool(name, args)

        if hasattr(raw_result, "data") and raw_result.data is not None:
            return str(raw_result.data)

        if hasattr(raw_result, "content"):
            return str(raw_result.content)

        return str(raw_result)

    async def close(self) -> None:
        """Close the client session once."""
        if self._is_connected:
            try:
                await self.client.__aexit__(None, None, None)
            finally:
                self._is_connected = False
                self._tools = []
