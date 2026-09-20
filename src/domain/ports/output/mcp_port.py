"""Output port for MCP tooling and context.

Defines the contract the application uses to discover and invoke tools exposed
through the Model Context Protocol. The concrete implementation (e.g. a
streamable HTTP MCP server, a mock) is provided by the infrastructure layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class MCPTool:
    """Descriptor of a single MCP tool exposed to the host."""

    name: str
    description: str
    input_schema: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class MCPContentItem:
    """A single piece of tool output content (text, image, audio...)."""

    kind: str = "text"
    data: str = ""


@dataclass(frozen=True, slots=True)
class MCPResponse:
    """Result of invoking a single MCP tool."""

    content: tuple[MCPContentItem, ...]
    is_error: bool = False


class MCPServerPort(ABC):
    """Port for MCP tool discovery and invocation."""

    @abstractmethod
    async def list_tools(self) -> tuple[MCPTool, ...]:
        """Return the MCP tools currently exposed by the connected server."""

    @abstractmethod
    async def call_tool(self, name: str, arguments: Mapping[str, Any]) -> MCPResponse:
        """Invoke the named MCP tool with the given arguments."""
