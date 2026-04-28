"""Account (Chart of Accounts) tools."""

from __future__ import annotations

from typing import List

from mcp.types import TextContent, Tool

from errors import mutation_text, text
from wave_client import WaveClient

from ._common import edges, json_text, need_business


LIST_ACCOUNTS = """
query(
  $businessId: ID!, $page: Int!, $pageSize: Int!,
  $types: [AccountTypeValue!], $subtypes: [AccountSubtypeValue!],
  $excludedSubtypes: [AccountSubtypeValue!], $isArchived: Boolean
) {
  business(id: $businessId) {
    id
    accounts(
      page: $page, pageSize: $pageSize,
      types: $types, subtypes: $subtypes,
      excludedSubtypes: $excludedSubtypes, isArchived: $isArchived
    ) {
      pageInfo { currentPage totalPages totalCount }
      edges {
        node {
          id displayId name description normalBalanceType isArchived
          currency { code symbol }
          type { name normalBalanceType value }
          subtype { name value }
        }
      }
    }
  }
}
"""

GET_ACCOUNT = """
query($businessId: ID!, $accountId: ID!) {
  business(id: $businessId) {
    id
    account(id: $accountId) {
      id displayId name description normalBalanceType isArchived
      currency { code symbol }
      type { name normalBalanceType value }
      subtype { name value }
    }
  }
}
"""

CREATE_ACCOUNT = """
mutation($input: AccountCreateInput!) {
  accountCreate(input: $input) {
    didSucceed
    inputErrors { path message code }
    account {
      id name displayId
      type { name } subtype { name }
      currency { code }
    }
  }
}
"""

PATCH_ACCOUNT = """
mutation($input: AccountPatchInput!) {
  accountPatch(input: $input) {
    didSucceed
    inputErrors { path message code }
    account { id name displayId description }
  }
}
"""

ARCHIVE_ACCOUNT = """
mutation($input: AccountArchiveInput!) {
  accountArchive(input: $input) {
    didSucceed
    inputErrors { path message code }
  }
}
"""

LIST_ACCOUNT_TYPES = """
{ accountTypes { name value normalBalanceType } }
"""

LIST_ACCOUNT_SUBTYPES = """
{ accountSubtypes { name value type { name value } } }
"""


async def _list(client: WaveClient, args: dict) -> List[TextContent]:
    bid, err = need_business(client, args)
    if err:
        return err
    page = args.get("page", 1)
    page_size = args.get("page_size", 50)
    data = await client.request(
        LIST_ACCOUNTS,
        {
            "businessId": bid,
            "page": page,
            "pageSize": page_size,
            "types": args.get("types"),
            "subtypes": args.get("subtypes"),
            "excludedSubtypes": args.get("excluded_subtypes"),
            "isArchived": args.get("is_archived"),
        },
    )
    payload = data["data"]["business"]["accounts"]
    return json_text({
        "pageInfo": payload["pageInfo"],
        "accounts": [e["node"] for e in payload["edges"]],
    })


async def _get(client: WaveClient, args: dict) -> List[TextContent]:
    bid, err = need_business(client, args)
    if err:
        return err
    data = await client.request(
        GET_ACCOUNT, {"businessId": bid, "accountId": args["account_id"]}
    )
    return json_text(data["data"]["business"]["account"])


async def _create(client: WaveClient, args: dict) -> List[TextContent]:
    bid, err = need_business(client, args)
    if err:
        return err
    inp = {
        "businessId": bid,
        "subtype": args["subtype"],
        "name": args["name"],
    }
    for k in ("currency", "description", "displayId"):
        if args.get(k) is not None:
            inp[k] = args[k]
    if args.get("can_archive") is not None:
        inp["restrictions"] = {"canArchive": args["can_archive"]}

    data = await client.request(CREATE_ACCOUNT, {"input": inp})
    res = data["data"]["accountCreate"]
    if res.get("didSucceed"):
        acc = res["account"]
        return text(
            f"✅ Created account '{acc['name']}'\n"
            f"  - ID: {acc['id']}\n"
            f"  - Type: {acc['type']['name']} / {acc['subtype']['name']}\n"
            f"  - Currency: {(acc.get('currency') or {}).get('code') or '(business default)'}"
        )
    return mutation_text(res, "", failure_prefix="❌ accountCreate failed")


async def _patch(client: WaveClient, args: dict) -> List[TextContent]:
    inp = {"id": args["account_id"], "sequence": args["sequence"]}
    for k in ("name", "description", "displayId"):
        if args.get(k) is not None:
            inp[k] = args[k]
    data = await client.request(PATCH_ACCOUNT, {"input": inp})
    res = data["data"]["accountPatch"]
    if res.get("didSucceed"):
        acc = res["account"]
        return text(f"✅ Patched account '{acc['name']}' ({acc['id']})")
    return mutation_text(res, "", failure_prefix="❌ accountPatch failed")


async def _archive(client: WaveClient, args: dict) -> List[TextContent]:
    inp = {"id": args["account_id"]}
    data = await client.request(ARCHIVE_ACCOUNT, {"input": inp})
    res = data["data"]["accountArchive"]
    return mutation_text(
        res,
        f"✅ Archived account {args['account_id']}",
        failure_prefix="❌ accountArchive failed",
    )


async def _types(client: WaveClient, _args: dict) -> List[TextContent]:
    data = await client.request(LIST_ACCOUNT_TYPES)
    return json_text(data["data"]["accountTypes"])


async def _subtypes(client: WaveClient, _args: dict) -> List[TextContent]:
    data = await client.request(LIST_ACCOUNT_SUBTYPES)
    return json_text(data["data"]["accountSubtypes"])


def tools():
    yield (
        Tool(
            name="list_accounts",
            description=(
                "List the chart of accounts for a business. Optionally filter by `types` "
                "(e.g. ['ASSET','EXPENSE','INCOME','LIABILITY','EQUITY'])."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "business_id": {"type": "string"},
                    "types": {
                        "type": "array",
                        "description": "Optional account type filter (uppercase Wave enum values)",
                        "items": {
                            "type": "string",
                            "enum": ["ASSET", "EQUITY", "EXPENSE", "INCOME", "LIABILITY"],
                        },
                    },
                    "subtypes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional subtype filter (e.g. CASH_AND_BANK, EXPENSE)",
                    },
                    "excluded_subtypes": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
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
            name="get_account",
            description="Fetch one account by ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_id": {"type": "string"},
                    "account_id": {"type": "string"},
                },
                "required": ["account_id"],
            },
        ),
        _get,
    )
    yield (
        Tool(
            name="create_account",
            description=(
                "Create a new account in the chart of accounts. Use `list_account_subtypes` "
                "to find the right `subtype` value (e.g. CASH_AND_BANK, EXPENSE, INCOME)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "business_id": {"type": "string"},
                    "name": {"type": "string"},
                    "subtype": {
                        "type": "string",
                        "description": "AccountSubtypeValueCreateInput enum (uppercase, see list_account_subtypes)",
                    },
                    "currency": {
                        "type": "string",
                        "description": "ISO currency code (e.g. CAD, USD); defaults to the business currency",
                    },
                    "description": {"type": "string"},
                    "displayId": {"type": "string", "description": "Optional display number/code"},
                    "can_archive": {"type": "boolean", "description": "If false, prevents archiving"},
                },
                "required": ["name", "subtype"],
            },
        ),
        _create,
    )
    yield (
        Tool(
            name="patch_account",
            description=(
                "Patch an account (name/description/displayId). `sequence` is required by Wave's "
                "optimistic concurrency control — pass the value returned in the latest read."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "account_id": {"type": "string"},
                    "sequence": {"type": "integer"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "displayId": {"type": "string"},
                },
                "required": ["account_id", "sequence"],
            },
        ),
        _patch,
    )
    yield (
        Tool(
            name="archive_account",
            description="Archive (soft-delete) an account.",
            inputSchema={
                "type": "object",
                "properties": {
                    "account_id": {"type": "string"},
                },
                "required": ["account_id"],
            },
        ),
        _archive,
    )
    yield (
        Tool(
            name="list_account_types",
            description="List all account types Wave supports (ASSET, EXPENSE, INCOME, LIABILITY, EQUITY).",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        _types,
    )
    yield (
        Tool(
            name="list_account_subtypes",
            description=(
                "List all account subtypes with their parent type. Use the `value` field for "
                "create_account's `subtype` parameter."
            ),
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        _subtypes,
    )
