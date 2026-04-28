"""Sales tax tools."""

from __future__ import annotations

from typing import List

from mcp.types import TextContent, Tool

from errors import mutation_text, text
from wave_client import WaveClient

from ._common import json_text, need_business


SALES_TAX_FIELDS = """
id name abbreviation description rate
taxNumber showTaxNumberOnInvoices isCompound isRecoverable
isArchived createdAt modifiedAt
"""

LIST_SALES_TAXES = f"""
query($businessId: ID!, $page: Int!, $pageSize: Int!, $isArchived: Boolean) {{
  business(id: $businessId) {{
    id
    salesTaxes(page: $page, pageSize: $pageSize, isArchived: $isArchived) {{
      pageInfo {{ currentPage totalPages totalCount }}
      edges {{ node {{ {SALES_TAX_FIELDS} }} }}
    }}
  }}
}}
"""

GET_SALES_TAX = f"""
query($businessId: ID!, $id: ID!) {{
  business(id: $businessId) {{ id salesTax(id: $id) {{ {SALES_TAX_FIELDS} }} }}
}}
"""

CREATE_SALES_TAX = f"""
mutation($input: SalesTaxCreateInput!) {{
  salesTaxCreate(input: $input) {{
    didSucceed inputErrors {{ path message code }}
    salesTax {{ {SALES_TAX_FIELDS} }}
  }}
}}
"""

PATCH_SALES_TAX = f"""
mutation($input: SalesTaxPatchInput!) {{
  salesTaxPatch(input: $input) {{
    didSucceed inputErrors {{ path message code }}
    salesTax {{ {SALES_TAX_FIELDS} }}
  }}
}}
"""

ARCHIVE_SALES_TAX = """
mutation($input: SalesTaxArchiveInput!) {
  salesTaxArchive(input: $input) {
    didSucceed inputErrors { path message code }
    salesTax { id name isArchived }
  }
}
"""

_TAX_FIELDS = {
    "name": {"type": "string"},
    "abbreviation": {"type": "string"},
    "rate": {"type": "number", "description": "Decimal percentage, e.g. 5 for 5%"},
    "description": {"type": "string"},
    "taxNumber": {"type": "string"},
    "showTaxNumberOnInvoices": {"type": "boolean"},
    "isCompound": {"type": "boolean"},
    "isRecoverable": {"type": "boolean"},
}


async def _list(client: WaveClient, args: dict) -> List[TextContent]:
    bid, err = need_business(client, args)
    if err:
        return err
    data = await client.request(
        LIST_SALES_TAXES,
        {
            "businessId": bid,
            "page": args.get("page", 1),
            "pageSize": args.get("page_size", 50),
            "isArchived": args.get("is_archived"),
        },
    )
    p = data["data"]["business"]["salesTaxes"]
    return json_text({"pageInfo": p["pageInfo"], "salesTaxes": [e["node"] for e in p["edges"]]})


async def _get(client: WaveClient, args: dict) -> List[TextContent]:
    bid, err = need_business(client, args)
    if err:
        return err
    data = await client.request(GET_SALES_TAX, {"businessId": bid, "id": args["sales_tax_id"]})
    return json_text(data["data"]["business"]["salesTax"])


def _build_input(args: dict, business_id: str | None = None) -> dict:
    inp = {}
    if business_id:
        inp["businessId"] = business_id
    for k in _TAX_FIELDS:
        if args.get(k) is not None:
            inp[k] = args[k]
    return inp


async def _create(client: WaveClient, args: dict) -> List[TextContent]:
    bid, err = need_business(client, args)
    if err:
        return err
    inp = _build_input(args, bid)
    data = await client.request(CREATE_SALES_TAX, {"input": inp})
    res = data["data"]["salesTaxCreate"]
    if res.get("didSucceed"):
        t = res["salesTax"]
        return text(f"✅ Created sales tax '{t['name']}' ({t['id']}) at {t['rate']}%")
    return mutation_text(res, "", failure_prefix="❌ salesTaxCreate failed")


async def _patch(client: WaveClient, args: dict) -> List[TextContent]:
    inp = _build_input(args)
    inp["id"] = args["sales_tax_id"]
    data = await client.request(PATCH_SALES_TAX, {"input": inp})
    res = data["data"]["salesTaxPatch"]
    if res.get("didSucceed"):
        t = res["salesTax"]
        return text(f"✅ Patched sales tax '{t['name']}' ({t['id']})")
    return mutation_text(res, "", failure_prefix="❌ salesTaxPatch failed")


async def _archive(client: WaveClient, args: dict) -> List[TextContent]:
    data = await client.request(ARCHIVE_SALES_TAX, {"input": {"id": args["sales_tax_id"]}})
    res = data["data"]["salesTaxArchive"]
    if res.get("didSucceed"):
        t = res["salesTax"]
        return text(f"✅ Archived sales tax '{t['name']}' ({t['id']})")
    return mutation_text(res, "", failure_prefix="❌ salesTaxArchive failed")


def tools():
    yield (
        Tool(
            name="list_sales_taxes",
            description="List sales taxes for a business.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_id": {"type": "string"},
                    "is_archived": {"type": "boolean"},
                    "page": {"type": "integer", "default": 1, "minimum": 1},
                    "page_size": {"type": "integer", "default": 50, "minimum": 1, "maximum": 200},
                },
            },
        ),
        _list,
    )
    yield (
        Tool(
            name="get_sales_tax",
            description="Fetch a sales tax by ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_id": {"type": "string"},
                    "sales_tax_id": {"type": "string"},
                },
                "required": ["sales_tax_id"],
            },
        ),
        _get,
    )
    yield (
        Tool(
            name="create_sales_tax",
            description="Create a sales tax (e.g. GST 5%, QST 9.975%).",
            inputSchema={
                "type": "object",
                "properties": {"business_id": {"type": "string"}, **_TAX_FIELDS},
                "required": ["name", "abbreviation", "rate"],
            },
        ),
        _create,
    )
    yield (
        Tool(
            name="patch_sales_tax",
            description="Patch an existing sales tax.",
            inputSchema={
                "type": "object",
                "properties": {"sales_tax_id": {"type": "string"}, **_TAX_FIELDS},
                "required": ["sales_tax_id"],
            },
        ),
        _patch,
    )
    yield (
        Tool(
            name="archive_sales_tax",
            description="Archive a sales tax.",
            inputSchema={
                "type": "object",
                "properties": {"sales_tax_id": {"type": "string"}},
                "required": ["sales_tax_id"],
            },
        ),
        _archive,
    )
