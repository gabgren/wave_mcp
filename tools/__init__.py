"""Aggregate every Wave MCP tool from each domain module."""

from __future__ import annotations

from typing import Awaitable, Callable, Dict, List

from mcp.types import TextContent, Tool

from wave_client import WaveClient

from . import (
    accounts,
    businesses,
    customers,
    estimates,
    invoices,
    legacy,
    products,
    reference,
    sales_taxes,
    transactions,
    vendors,
)

ToolHandler = Callable[[WaveClient, dict], Awaitable[List[TextContent]]]


def all_tools() -> Dict[str, tuple]:
    """Return {tool_name: (Tool, handler)}."""
    registry: Dict[str, tuple] = {}
    for module in (
        businesses,
        accounts,
        reference,
        customers,
        vendors,
        products,
        sales_taxes,
        transactions,
        invoices,
        estimates,
        legacy,
    ):
        for tool, handler in module.tools():
            if tool.name in registry:
                raise RuntimeError(f"Duplicate tool name: {tool.name}")
            registry[tool.name] = (tool, handler)
    return registry
