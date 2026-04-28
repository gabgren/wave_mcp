"""Money-transaction tools.

Wave's `moneyTransactionCreate` is one mutation that expresses expenses, income,
transfers, and arbitrary journal entries depending on what accounts you point
the anchor and line items at. We expose four ergonomic variants plus a generic
escape hatch.
"""

from __future__ import annotations

from datetime import datetime
from typing import List

from mcp.types import TextContent, Tool

from errors import mutation_text, text
from wave_client import WaveClient

from ._common import need_business


CREATE_MONEY_TRANSACTION = """
mutation($input: MoneyTransactionCreateInput!) {
  moneyTransactionCreate(input: $input) {
    didSucceed
    inputErrors { path message code }
    transaction { id }
  }
}
"""

CREATE_MONEY_TRANSACTIONS_BULK = """
mutation($input: MoneyTransactionsCreateInput!) {
  moneyTransactionsCreate(input: $input) {
    didSucceed
    inputErrors { path message code }
    transactions { id }
  }
}
"""


def _line_item_input_schema(simple: bool = True) -> dict:
    """Schema for a transaction line item."""
    return {
        "type": "object",
        "properties": {
            "accountId": {"type": "string"},
            "amount": {"type": "number"},
            "balance": {
                "type": "string",
                "enum": ["INCREASE", "DECREASE"],
                "description": "Whether this line increases or decreases the account balance",
            },
            "customerId": {"type": "string", "description": "Optional"},
            "description": {"type": "string"},
            "taxes": {
                "type": "array",
                "description": "Optional list of {salesTaxId, amount} entries",
                "items": {
                    "type": "object",
                    "properties": {
                        "salesTaxId": {"type": "string"},
                        "amount": {"type": "number"},
                    },
                    "required": ["salesTaxId", "amount"],
                },
            },
        },
        "required": ["accountId", "amount", "balance"],
    }


def _anchor_input_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "accountId": {"type": "string", "description": "Bank/credit-card/asset account"},
            "amount": {"type": "number"},
            "direction": {
                "type": "string",
                "enum": ["DEPOSIT", "WITHDRAWAL"],
                "description": "DEPOSIT = money in; WITHDRAWAL = money out",
            },
        },
        "required": ["accountId", "amount", "direction"],
    }


def _ext_id(prefix: str) -> str:
    return f"{prefix}-{datetime.now().isoformat()}"


async def _create_money_transaction(client: WaveClient, args: dict) -> List[TextContent]:
    bid, err = need_business(client, args)
    if err:
        return err

    inp = {
        "businessId": bid,
        "externalId": args.get("external_id") or _ext_id("tx"),
        "date": args["date"],
        "description": args["description"],
        "anchor": args["anchor"],
        "lineItems": args["line_items"],
    }
    if args.get("notes") is not None:
        inp["notes"] = args["notes"]

    data = await client.request(CREATE_MONEY_TRANSACTION, {"input": inp})
    res = data["data"]["moneyTransactionCreate"]
    if res.get("didSucceed"):
        return text(f"✅ Created money transaction (ID: {res['transaction']['id']})")
    return mutation_text(res, "", failure_prefix="❌ moneyTransactionCreate failed")


async def _create_transfer(client: WaveClient, args: dict) -> List[TextContent]:
    """Transfer between two of your own accounts."""
    bid, err = need_business(client, args)
    if err:
        return err

    amount = args["amount"]
    inp = {
        "businessId": bid,
        "externalId": args.get("external_id") or _ext_id("transfer"),
        "date": args["date"],
        "description": args.get("description") or "Account transfer",
        "anchor": {
            "accountId": args["from_account_id"],
            "amount": amount,
            "direction": "WITHDRAWAL",
        },
        "lineItems": [
            {
                "accountId": args["to_account_id"],
                "amount": amount,
                "balance": "INCREASE",
            }
        ],
    }
    if args.get("notes") is not None:
        inp["notes"] = args["notes"]

    data = await client.request(CREATE_MONEY_TRANSACTION, {"input": inp})
    res = data["data"]["moneyTransactionCreate"]
    if res.get("didSucceed"):
        return text(
            f"✅ Created transfer of {amount} on {args['date']} "
            f"(ID: {res['transaction']['id']})"
        )
    return mutation_text(res, "", failure_prefix="❌ Transfer failed")


async def _create_journal_entry(client: WaveClient, args: dict) -> List[TextContent]:
    """General journal entry: any anchor + multiple line items, including Equity/Liability."""
    return await _create_money_transaction(client, args)


async def _create_bulk(client: WaveClient, args: dict) -> List[TextContent]:
    bid, err = need_business(client, args)
    if err:
        return err

    txs = []
    for t in args["transactions"]:
        entry = {
            "externalId": t.get("external_id") or _ext_id("bulk"),
            "date": t["date"],
            "description": t["description"],
            "anchor": t["anchor"],
            "lineItems": t["line_items"],
        }
        if t.get("notes") is not None:
            entry["notes"] = t["notes"]
        txs.append(entry)

    inp = {"businessId": bid, "transactions": txs}
    data = await client.request(CREATE_MONEY_TRANSACTIONS_BULK, {"input": inp})
    res = data["data"]["moneyTransactionsCreate"]
    if res.get("didSucceed"):
        ids = [t["id"] for t in (res.get("transactions") or [])]
        return text(f"✅ Created {len(ids)} transactions: {', '.join(ids)}")
    return mutation_text(res, "", failure_prefix="❌ moneyTransactionsCreate failed")


def tools():
    yield (
        Tool(
            name="create_money_transaction",
            description=(
                "General-purpose money transaction (works for expenses, income, transfers, "
                "and journal entries). For convenience use create_transfer / "
                "create_expense_from_receipt / create_income_from_payment when applicable."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "business_id": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "description": {"type": "string"},
                    "external_id": {
                        "type": "string",
                        "description": "Idempotency key. Auto-generated if omitted.",
                    },
                    "notes": {"type": "string"},
                    "anchor": _anchor_input_schema(),
                    "line_items": {
                        "type": "array",
                        "items": _line_item_input_schema(),
                        "minItems": 1,
                    },
                },
                "required": ["date", "description", "anchor", "line_items"],
            },
        ),
        _create_money_transaction,
    )

    yield (
        Tool(
            name="create_transfer",
            description="Transfer money between two of your own accounts.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_id": {"type": "string"},
                    "from_account_id": {"type": "string"},
                    "to_account_id": {"type": "string"},
                    "amount": {"type": "number"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "description": {"type": "string"},
                    "external_id": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": ["from_account_id", "to_account_id", "amount", "date"],
            },
        ),
        _create_transfer,
    )

    yield (
        Tool(
            name="create_journal_entry",
            description=(
                "Alias for create_money_transaction with semantics oriented toward "
                "non-bank entries (e.g. owner draws posting to Equity). Same input shape."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "business_id": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "description": {"type": "string"},
                    "external_id": {"type": "string"},
                    "notes": {"type": "string"},
                    "anchor": _anchor_input_schema(),
                    "line_items": {
                        "type": "array",
                        "items": _line_item_input_schema(),
                        "minItems": 1,
                    },
                },
                "required": ["date", "description", "anchor", "line_items"],
            },
        ),
        _create_journal_entry,
    )

    yield (
        Tool(
            name="create_transactions_bulk",
            description=(
                "Create many money transactions in a single API call. Useful for importing "
                "bank statements. Same per-transaction shape as create_money_transaction."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "business_id": {"type": "string"},
                    "transactions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "date": {"type": "string"},
                                "description": {"type": "string"},
                                "external_id": {"type": "string"},
                                "notes": {"type": "string"},
                                "anchor": _anchor_input_schema(),
                                "line_items": {
                                    "type": "array",
                                    "items": _line_item_input_schema(),
                                },
                            },
                            "required": ["date", "description", "anchor", "line_items"],
                        },
                        "minItems": 1,
                    },
                },
                "required": ["transactions"],
            },
        ),
        _create_bulk,
    )
