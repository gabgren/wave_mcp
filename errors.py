"""Standardized error formatting for Wave mutation responses."""

from __future__ import annotations

from typing import List, Optional

from mcp.types import TextContent


def format_input_errors(input_errors: Optional[list]) -> str:
    """Render Wave's inputErrors[] into a human-readable string."""
    if not input_errors:
        return "(no error details)"
    parts = []
    for err in input_errors:
        path = err.get("path") or "?"
        msg = err.get("message") or "(no message)"
        code = err.get("code")
        parts.append(f"  - {path}: {msg}" + (f" [{code}]" if code else ""))
    return "\n".join(parts)


def mutation_text(
    payload: dict,
    success_message: str,
    failure_prefix: str = "Failed",
) -> List[TextContent]:
    """Convert a mutation payload {didSucceed, inputErrors, ...} → MCP text content."""
    if payload.get("didSucceed"):
        return [TextContent(type="text", text=success_message)]
    return [
        TextContent(
            type="text",
            text=f"{failure_prefix}:\n{format_input_errors(payload.get('inputErrors'))}",
        )
    ]


def text(s: str) -> List[TextContent]:
    return [TextContent(type="text", text=s)]
