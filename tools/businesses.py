"""Business-level tools: list, get, set active."""

from __future__ import annotations

from typing import List

from mcp.types import TextContent, Tool

from errors import text
from wave_client import WaveClient

from ._common import json_text


LIST_BUSINESSES = """
query($page: Int!, $pageSize: Int!) {
  businesses(page: $page, pageSize: $pageSize) {
    pageInfo { currentPage totalPages totalCount }
    edges {
      node { id name isPersonal isClassicAccounting isArchived currency { code } timezone }
    }
  }
}
"""

GET_BUSINESS = """
query($id: ID!) {
  business(id: $id) {
    id name isPersonal isClassicAccounting isArchived
    organizationalType
    currency { code symbol }
    timezone
    address { addressLine1 addressLine2 city province { name code } postalCode country { name code } }
    phone fax mobile tollFree website
    createdAt modifiedAt
    emailSendEnabled
  }
}
"""


async def _list(client: WaveClient, args: dict) -> List[TextContent]:
    page = args.get("page", 1)
    page_size = args.get("page_size", 25)
    data = await client.request(LIST_BUSINESSES, {"page": page, "pageSize": page_size})
    return json_text(data["data"]["businesses"])


async def _get(client: WaveClient, args: dict) -> List[TextContent]:
    bid = args.get("business_id") or client.business_id
    if not bid:
        return text("Error: provide `business_id` or call set_business first.")
    data = await client.request(GET_BUSINESS, {"id": bid})
    return json_text(data["data"]["business"])


async def _set(client: WaveClient, args: dict) -> List[TextContent]:
    client.business_id = args["business_id"]
    return text(f"Active business set to: {client.business_id}")


def tools():
    yield (
        Tool(
            name="list_businesses",
            description="List Wave businesses available to the authenticated user.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page": {"type": "integer", "default": 1, "minimum": 1},
                    "page_size": {"type": "integer", "default": 25, "minimum": 1, "maximum": 200},
                },
                "additionalProperties": False,
            },
        ),
        _list,
    )
    yield (
        Tool(
            name="get_business",
            description="Get full details for a specific Wave business.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_id": {
                        "type": "string",
                        "description": "Wave business ID; defaults to the active business",
                    }
                },
            },
        ),
        _get,
    )
    yield (
        Tool(
            name="set_business",
            description="Set the active Wave business for subsequent tool calls.",
            inputSchema={
                "type": "object",
                "properties": {"business_id": {"type": "string"}},
                "required": ["business_id"],
            },
        ),
        _set,
    )
