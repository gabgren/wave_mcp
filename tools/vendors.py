"""Vendor tools (read-only — Wave's public API does not expose vendor mutations)."""

from __future__ import annotations

from typing import List

from mcp.types import TextContent, Tool

from wave_client import WaveClient

from ._common import json_text, need_business


VENDOR_FIELDS = """
id name firstName lastName displayId email mobile phone fax tollFree website internalNotes
currency { code }
address { addressLine1 addressLine2 city province { name code } postalCode country { name code } }
isArchived createdAt modifiedAt
"""

LIST_VENDORS = f"""
query($businessId: ID!, $page: Int!, $pageSize: Int!, $email: String) {{
  business(id: $businessId) {{
    id
    vendors(page: $page, pageSize: $pageSize, email: $email) {{
      pageInfo {{ currentPage totalPages totalCount }}
      edges {{ node {{ {VENDOR_FIELDS} }} }}
    }}
  }}
}}
"""

GET_VENDOR = f"""
query($businessId: ID!, $id: ID!) {{
  business(id: $businessId) {{ id vendor(id: $id) {{ {VENDOR_FIELDS} }} }}
}}
"""


async def _list(client: WaveClient, args: dict) -> List[TextContent]:
    bid, err = need_business(client, args)
    if err:
        return err
    data = await client.request(
        LIST_VENDORS,
        {
            "businessId": bid,
            "page": args.get("page", 1),
            "pageSize": args.get("page_size", 50),
            "email": args.get("email"),
        },
    )
    p = data["data"]["business"]["vendors"]
    return json_text({"pageInfo": p["pageInfo"], "vendors": [e["node"] for e in p["edges"]]})


async def _get(client: WaveClient, args: dict) -> List[TextContent]:
    bid, err = need_business(client, args)
    if err:
        return err
    data = await client.request(GET_VENDOR, {"businessId": bid, "id": args["vendor_id"]})
    return json_text(data["data"]["business"]["vendor"])


def tools():
    yield (
        Tool(
            name="list_vendors",
            description=(
                "List vendors. Note: Wave's public API does not allow creating, updating, "
                "or deleting vendors — those must be done in Wave's web UI."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "business_id": {"type": "string"},
                    "email": {"type": "string"},
                    "page": {"type": "integer", "default": 1, "minimum": 1},
                    "page_size": {"type": "integer", "default": 50, "minimum": 1, "maximum": 200},
                },
            },
        ),
        _list,
    )
    yield (
        Tool(
            name="get_vendor",
            description="Fetch a vendor by ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_id": {"type": "string"},
                    "vendor_id": {"type": "string"},
                },
                "required": ["vendor_id"],
            },
        ),
        _get,
    )
