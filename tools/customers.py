"""Customer tools."""

from __future__ import annotations

from typing import List

from mcp.types import TextContent, Tool

from errors import mutation_text, text
from wave_client import WaveClient

from ._common import json_text, need_business


CUSTOMER_FIELDS = """
id internalId name firstName lastName displayId email mobile phone fax tollFree website internalNotes
currency { code }
address { addressLine1 addressLine2 city province { name code } postalCode country { name code } }
shippingDetails { name phone instructions
  address { addressLine1 addressLine2 city province { name code } postalCode country { name code } } }
isArchived createdAt modifiedAt
"""

LIST_CUSTOMERS = f"""
query($businessId: ID!, $page: Int!, $pageSize: Int!, $sort: [CustomerSort!]!, $email: String) {{
  business(id: $businessId) {{
    id
    customers(page: $page, pageSize: $pageSize, sort: $sort, email: $email) {{
      pageInfo {{ currentPage totalPages totalCount }}
      edges {{ node {{ {CUSTOMER_FIELDS} }} }}
    }}
  }}
}}
"""

GET_CUSTOMER = f"""
query($businessId: ID!, $id: ID!) {{
  business(id: $businessId) {{ id customer(id: $id) {{ {CUSTOMER_FIELDS} }} }}
}}
"""

CREATE_CUSTOMER = f"""
mutation($input: CustomerCreateInput!) {{
  customerCreate(input: $input) {{
    didSucceed
    inputErrors {{ path message code }}
    customer {{ {CUSTOMER_FIELDS} }}
  }}
}}
"""

PATCH_CUSTOMER = f"""
mutation($input: CustomerPatchInput!) {{
  customerPatch(input: $input) {{
    didSucceed
    inputErrors {{ path message code }}
    customer {{ {CUSTOMER_FIELDS} }}
  }}
}}
"""

DELETE_CUSTOMER = """
mutation($input: CustomerDeleteInput!) {
  customerDelete(input: $input) { didSucceed inputErrors { path message code } }
}
"""


def _address_schema():
    return {
        "type": "object",
        "properties": {
            "addressLine1": {"type": "string"},
            "addressLine2": {"type": "string"},
            "city": {"type": "string"},
            "provinceCode": {"type": "string"},
            "countryCode": {"type": "string", "description": "ISO 3166-1 alpha-2 (e.g. CA, US)"},
            "postalCode": {"type": "string"},
        },
        "additionalProperties": False,
    }


def _shipping_schema():
    return {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "phone": {"type": "string"},
            "instructions": {"type": "string"},
            "address": _address_schema(),
        },
        "additionalProperties": False,
    }


_CUSTOMER_FIELDS_SCHEMA = {
    "name": {"type": "string"},
    "firstName": {"type": "string"},
    "lastName": {"type": "string"},
    "address": _address_schema(),
    "displayId": {"type": "string"},
    "email": {"type": "string"},
    "mobile": {"type": "string"},
    "phone": {"type": "string"},
    "fax": {"type": "string"},
    "tollFree": {"type": "string"},
    "website": {"type": "string"},
    "internalNotes": {"type": "string"},
    "currency": {"type": "string"},
    "shippingDetails": _shipping_schema(),
}


def _customer_input(args: dict, business_id: str | None = None) -> dict:
    inp = {}
    if business_id:
        inp["businessId"] = business_id
    for k in _CUSTOMER_FIELDS_SCHEMA:
        if args.get(k) is not None:
            inp[k] = args[k]
    return inp


async def _list(client: WaveClient, args: dict) -> List[TextContent]:
    bid, err = need_business(client, args)
    if err:
        return err
    sort = args.get("sort") or ["NAME_ASC"]
    data = await client.request(
        LIST_CUSTOMERS,
        {
            "businessId": bid,
            "page": args.get("page", 1),
            "pageSize": args.get("page_size", 50),
            "sort": sort,
            "email": args.get("email"),
        },
    )
    payload = data["data"]["business"]["customers"]
    return json_text({
        "pageInfo": payload["pageInfo"],
        "customers": [e["node"] for e in payload["edges"]],
    })


async def _get(client: WaveClient, args: dict) -> List[TextContent]:
    bid, err = need_business(client, args)
    if err:
        return err
    data = await client.request(GET_CUSTOMER, {"businessId": bid, "id": args["customer_id"]})
    return json_text(data["data"]["business"]["customer"])


async def _create(client: WaveClient, args: dict) -> List[TextContent]:
    bid, err = need_business(client, args)
    if err:
        return err
    inp = _customer_input(args, bid)
    inp["name"] = args["name"]
    data = await client.request(CREATE_CUSTOMER, {"input": inp})
    res = data["data"]["customerCreate"]
    if res.get("didSucceed"):
        c = res["customer"]
        return text(f"✅ Created customer '{c['name']}' (ID: {c['id']})")
    return mutation_text(res, "", failure_prefix="❌ customerCreate failed")


async def _patch(client: WaveClient, args: dict) -> List[TextContent]:
    inp = _customer_input(args)
    inp["id"] = args["customer_id"]
    data = await client.request(PATCH_CUSTOMER, {"input": inp})
    res = data["data"]["customerPatch"]
    if res.get("didSucceed"):
        c = res["customer"]
        return text(f"✅ Patched customer '{c['name']}' ({c['id']})")
    return mutation_text(res, "", failure_prefix="❌ customerPatch failed")


async def _delete(client: WaveClient, args: dict) -> List[TextContent]:
    data = await client.request(DELETE_CUSTOMER, {"input": {"id": args["customer_id"]}})
    res = data["data"]["customerDelete"]
    return mutation_text(
        res,
        f"✅ Deleted customer {args['customer_id']}",
        failure_prefix="❌ customerDelete failed",
    )


def tools():
    yield (
        Tool(
            name="list_customers",
            description="List customers for a business.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_id": {"type": "string"},
                    "email": {"type": "string", "description": "Optional email filter"},
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
            name="get_customer",
            description="Fetch a customer by ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_id": {"type": "string"},
                    "customer_id": {"type": "string"},
                },
                "required": ["customer_id"],
            },
        ),
        _get,
    )
    yield (
        Tool(
            name="create_customer",
            description="Create a customer in Wave.",
            inputSchema={
                "type": "object",
                "properties": {"business_id": {"type": "string"}, **_CUSTOMER_FIELDS_SCHEMA},
                "required": ["name"],
            },
        ),
        _create,
    )
    yield (
        Tool(
            name="patch_customer",
            description="Update fields on an existing customer (omit to leave unchanged).",
            inputSchema={
                "type": "object",
                "properties": {"customer_id": {"type": "string"}, **_CUSTOMER_FIELDS_SCHEMA},
                "required": ["customer_id"],
            },
        ),
        _patch,
    )
    yield (
        Tool(
            name="delete_customer",
            description="Delete a customer.",
            inputSchema={
                "type": "object",
                "properties": {"customer_id": {"type": "string"}},
                "required": ["customer_id"],
            },
        ),
        _delete,
    )
