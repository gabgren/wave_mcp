"""Shared helpers for tool modules."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from mcp.types import TextContent

from wave_client import WaveClient


def require_business(client: WaveClient, args: dict) -> Optional[str]:
    """Return business_id from args, falling back to the active one. None if unset."""
    return args.get("business_id") or client.business_id


def need_business(client: WaveClient, args: dict) -> tuple[Optional[str], Optional[List[TextContent]]]:
    """Tuple of (business_id, error_text_or_None)."""
    bid = require_business(client, args)
    if not bid:
        return None, [
            TextContent(
                type="text",
                text=(
                    "Error: No business selected. Pass `business_id` or call "
                    "`set_business` first (use `list_businesses` to find IDs)."
                ),
            )
        ]
    return bid, None


def json_text(data: Any) -> List[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]


def edges(payload: Dict[str, Any], path: List[str]) -> List[Dict[str, Any]]:
    """Walk into payload along `path` and return the connection edges."""
    cur = payload
    for p in path:
        cur = cur[p]
    return [e["node"] for e in cur.get("edges", [])]


def page_info(payload: Dict[str, Any], path: List[str]) -> Dict[str, Any]:
    cur = payload
    for p in path:
        cur = cur[p]
    return cur.get("pageInfo", {})


PAGINATION_SCHEMA = {
    "page": {
        "type": "integer",
        "description": "Page number (1-based)",
        "default": 1,
        "minimum": 1,
    },
    "page_size": {
        "type": "integer",
        "description": "Page size",
        "default": 25,
        "minimum": 1,
        "maximum": 200,
    },
}

BUSINESS_ID_SCHEMA = {
    "type": "string",
    "description": "Wave business ID; defaults to the active business set via set_business",
}
