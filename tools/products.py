"""Product/service tools."""

from __future__ import annotations

from typing import List

from mcp.types import TextContent, Tool

from errors import mutation_text, text
from wave_client import WaveClient

from ._common import json_text, need_business


PRODUCT_FIELDS = """
id name description unitPrice
isArchived isSold isBought createdAt modifiedAt
defaultSalesTaxes { id name rate }
incomeAccount { id name }
expenseAccount { id name }
"""

LIST_PRODUCTS = f"""
query(
  $businessId: ID!, $page: Int!, $pageSize: Int!, $sort: [ProductSort!]!,
  $isSold: Boolean, $isBought: Boolean, $isArchived: Boolean
) {{
  business(id: $businessId) {{
    id
    products(
      page: $page, pageSize: $pageSize, sort: $sort,
      isSold: $isSold, isBought: $isBought, isArchived: $isArchived
    ) {{
      pageInfo {{ currentPage totalPages totalCount }}
      edges {{ node {{ {PRODUCT_FIELDS} }} }}
    }}
  }}
}}
"""

GET_PRODUCT = f"""
query($businessId: ID!, $id: ID!) {{
  business(id: $businessId) {{ id product(id: $id) {{ {PRODUCT_FIELDS} }} }}
}}
"""

CREATE_PRODUCT = f"""
mutation($input: ProductCreateInput!) {{
  productCreate(input: $input) {{
    didSucceed
    inputErrors {{ path message code }}
    product {{ {PRODUCT_FIELDS} }}
  }}
}}
"""

PATCH_PRODUCT = f"""
mutation($input: ProductPatchInput!) {{
  productPatch(input: $input) {{
    didSucceed
    inputErrors {{ path message code }}
    product {{ {PRODUCT_FIELDS} }}
  }}
}}
"""

ARCHIVE_PRODUCT = """
mutation($input: ProductArchiveInput!) {
  productArchive(input: $input) {
    didSucceed inputErrors { path message code }
    product { id name isArchived }
  }
}
"""


async def _list(client: WaveClient, args: dict) -> List[TextContent]:
    bid, err = need_business(client, args)
    if err:
        return err
    data = await client.request(
        LIST_PRODUCTS,
        {
            "businessId": bid,
            "page": args.get("page", 1),
            "pageSize": args.get("page_size", 50),
            "sort": args.get("sort") or ["NAME_ASC"],
            "isSold": args.get("is_sold"),
            "isBought": args.get("is_bought"),
            "isArchived": args.get("is_archived"),
        },
    )
    p = data["data"]["business"]["products"]
    return json_text({"pageInfo": p["pageInfo"], "products": [e["node"] for e in p["edges"]]})


async def _get(client: WaveClient, args: dict) -> List[TextContent]:
    bid, err = need_business(client, args)
    if err:
        return err
    data = await client.request(GET_PRODUCT, {"businessId": bid, "id": args["product_id"]})
    return json_text(data["data"]["business"]["product"])


def _build_product_input(args: dict, business_id: str | None = None) -> dict:
    inp = {}
    if business_id:
        inp["businessId"] = business_id
    for k in ("name", "unitPrice", "description", "incomeAccountId", "expenseAccountId"):
        if args.get(k) is not None:
            inp[k] = args[k]
    if args.get("defaultSalesTaxIds") is not None:
        inp["defaultSalesTaxIds"] = args["defaultSalesTaxIds"]
    return inp


async def _create(client: WaveClient, args: dict) -> List[TextContent]:
    bid, err = need_business(client, args)
    if err:
        return err
    inp = _build_product_input(args, bid)
    data = await client.request(CREATE_PRODUCT, {"input": inp})
    res = data["data"]["productCreate"]
    if res.get("didSucceed"):
        p = res["product"]
        return text(f"✅ Created product '{p['name']}' (ID: {p['id']})")
    return mutation_text(res, "", failure_prefix="❌ productCreate failed")


async def _patch(client: WaveClient, args: dict) -> List[TextContent]:
    inp = _build_product_input(args)
    inp["id"] = args["product_id"]
    data = await client.request(PATCH_PRODUCT, {"input": inp})
    res = data["data"]["productPatch"]
    if res.get("didSucceed"):
        p = res["product"]
        return text(f"✅ Patched product '{p['name']}' ({p['id']})")
    return mutation_text(res, "", failure_prefix="❌ productPatch failed")


async def _archive(client: WaveClient, args: dict) -> List[TextContent]:
    data = await client.request(ARCHIVE_PRODUCT, {"input": {"id": args["product_id"]}})
    res = data["data"]["productArchive"]
    if res.get("didSucceed"):
        p = res["product"]
        return text(f"✅ Archived product '{p['name']}' ({p['id']})")
    return mutation_text(res, "", failure_prefix="❌ productArchive failed")


_PRODUCT_FIELD_SCHEMA = {
    "name": {"type": "string"},
    "unitPrice": {"type": "number", "description": "Default unit price"},
    "description": {"type": "string"},
    "incomeAccountId": {"type": "string", "description": "Default income account ID"},
    "expenseAccountId": {"type": "string", "description": "Default expense account ID"},
    "defaultSalesTaxIds": {"type": "array", "items": {"type": "string"}},
}


def tools():
    yield (
        Tool(
            name="list_products",
            description="List products and services.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_id": {"type": "string"},
                    "is_sold": {"type": "boolean"},
                    "is_bought": {"type": "boolean"},
                    "is_archived": {"type": "boolean"},
                    "sort": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "CREATED_AT_ASC", "CREATED_AT_DESC",
                                "MODIFIED_AT_ASC", "MODIFIED_AT_DESC",
                                "NAME_ASC", "NAME_DESC",
                            ],
                        },
                        "default": ["NAME_ASC"],
                    },
                    "page": {"type": "integer", "default": 1, "minimum": 1},
                    "page_size": {"type": "integer", "default": 50, "minimum": 1, "maximum": 200},
                },
            },
        ),
        _list,
    )
    yield (
        Tool(
            name="get_product",
            description="Fetch a product by ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_id": {"type": "string"},
                    "product_id": {"type": "string"},
                },
                "required": ["product_id"],
            },
        ),
        _get,
    )
    yield (
        Tool(
            name="create_product",
            description=(
                "Create a product or service. Wave requires at least one of "
                "`incomeAccountId` (sets isSold=true) or `expenseAccountId` "
                "(sets isBought=true). Pass both to mark the product as both sold and bought."
            ),
            inputSchema={
                "type": "object",
                "properties": {"business_id": {"type": "string"}, **_PRODUCT_FIELD_SCHEMA},
                "required": ["name", "unitPrice"],
            },
        ),
        _create,
    )
    yield (
        Tool(
            name="patch_product",
            description="Patch an existing product (omit fields to leave unchanged).",
            inputSchema={
                "type": "object",
                "properties": {"product_id": {"type": "string"}, **_PRODUCT_FIELD_SCHEMA},
                "required": ["product_id"],
            },
        ),
        _patch,
    )
    yield (
        Tool(
            name="archive_product",
            description="Archive a product.",
            inputSchema={
                "type": "object",
                "properties": {"product_id": {"type": "string"}},
                "required": ["product_id"],
            },
        ),
        _archive,
    )
