"""Legacy ergonomic tools that predate the modular layout.

`create_expense_from_receipt` and `create_income_from_payment` use fuzzy
matching on free-text categories. New callers should prefer
`create_money_transaction` with explicit account IDs."""

from __future__ import annotations

from datetime import datetime
from typing import List

from mcp.types import TextContent, Tool

from errors import text
from fuzzy import find_best_account_match
from wave_client import WaveClient

from ._common import need_business


GET_ACCOUNTS_LEGACY = """
query($businessId: ID!, $page: Int!, $pageSize: Int!) {
  business(id: $businessId) {
    id
    accounts(page: $page, pageSize: $pageSize) {
      pageInfo { currentPage totalPages totalCount }
      edges { node {
        id name displayId isArchived
        type { name normalBalanceType }
        subtype { name }
      } }
    }
  }
}
"""

GET_VENDORS_LEGACY = """
query($businessId: ID!) {
  business(id: $businessId) {
    id
    vendors { edges { node { id name email isArchived } } }
  }
}
"""

GET_CUSTOMERS_LEGACY = """
query($businessId: ID!) {
  business(id: $businessId) {
    id
    customers(page: 1, pageSize: 200, sort: [NAME_ASC]) {
      edges { node { id name email isArchived } }
    }
  }
}
"""

CREATE_TX = """
mutation($input: MoneyTransactionCreateInput!) {
  moneyTransactionCreate(input: $input) {
    didSucceed
    inputErrors { path message code }
    transaction { id }
  }
}
"""


async def _get_all_accounts(client: WaveClient, business_id: str) -> List[dict]:
    """Pull every account across all pages (used by fuzzy matcher)."""
    all_edges = []
    page = 1
    while True:
        data = await client.request(
            GET_ACCOUNTS_LEGACY,
            {"businessId": business_id, "page": page, "pageSize": 50},
        )
        payload = data["data"]["business"]["accounts"]
        all_edges.extend(payload["edges"])
        info = payload["pageInfo"]
        if info["currentPage"] >= info["totalPages"]:
            break
        page += 1
        if page > 20:
            break
    return all_edges


async def _create_expense_from_receipt(client: WaveClient, args: dict) -> List[TextContent]:
    bid, err = need_business(client, args)
    if err:
        return err

    vendor_name = args.get("vendor_name")
    amount = args["amount"]
    date = args["date"]
    category = args.get("category", "General Expenses")
    description = args.get("description", "")
    payment_account = args.get("payment_account")

    accounts = await _get_all_accounts(client, bid)

    # Find vendor (read-only — Wave doesn't allow vendor creation)
    vendor_id = None
    if vendor_name:
        v = await client.request(GET_VENDORS_LEGACY, {"businessId": bid})
        for vendor in v["data"]["business"]["vendors"]["edges"]:
            if vendor["node"]["name"].lower() == vendor_name.lower():
                vendor_id = vendor["node"]["id"]
                break

    expense_id, expense_name, score, explanation = find_best_account_match(
        category, accounts, "Expenses", description
    )
    if not expense_id:
        return text("Error: No expense accounts found")

    anchor_accounts = [
        a["node"] for a in accounts
        if a["node"]["type"]["name"] in ("Assets", "Liabilities & Credit Cards")
        and a["node"]["subtype"]["name"] in ("Cash & Bank", "Credit Card", "Loan and Line of Credit")
        and not a["node"]["isArchived"]
    ]
    if not anchor_accounts:
        return text("Error: No bank or credit card accounts found")

    anchor_id = anchor_name = None
    if payment_account:
        for a in anchor_accounts:
            if a["name"].lower() == payment_account.lower():
                anchor_id, anchor_name = a["id"], a["name"]
                break
        if not anchor_id:
            avail = "\n".join(f"- {a['name']}" for a in anchor_accounts)
            return text(f"❌ Payment account '{payment_account}' not found.\n\nAvailable:\n{avail}")
    if not anchor_id:
        anchor_id, anchor_name = anchor_accounts[0]["id"], anchor_accounts[0]["name"]

    inp = {
        "businessId": bid,
        "externalId": f"receipt-{datetime.now().isoformat()}",
        "date": date,
        "description": description or f"Expense - {vendor_name or 'Unknown Vendor'}",
        "anchor": {
            "accountId": anchor_id,
            "amount": float(amount),
            "direction": "WITHDRAWAL",
        },
        "lineItems": [{"accountId": expense_id, "amount": float(amount), "balance": "INCREASE"}],
    }

    data = await client.request(CREATE_TX, {"input": inp})
    res = data["data"]["moneyTransactionCreate"]
    if not res.get("didSucceed"):
        errs = ", ".join(f"{e['path']}: {e['message']}" for e in res["inputErrors"])
        return text(f"❌ Failed to create expense: {errs}")

    tid = res["transaction"]["id"]
    vendor_text = f"- Vendor: {vendor_name}" + ("" if vendor_id else " ⚠️ not in Wave")
    return text(
        f"✅ Created expense\n"
        f"- Amount: ${amount}\n"
        f"{vendor_text if vendor_name else '- Vendor: (not specified)'}\n"
        f"- Date: {date}\n"
        f"- Paid from: {anchor_name}\n"
        f"- Category: {category} → {expense_name} ({score:.1%})\n"
        f"  💡 {explanation}\n"
        f"- Transaction ID: {tid}"
    )


async def _create_income_from_payment(client: WaveClient, args: dict) -> List[TextContent]:
    bid, err = need_business(client, args)
    if err:
        return err

    customer_name = args.get("customer_name")
    amount = args["amount"]
    date = args["date"]
    income_category = args.get("income_category", "Sales")
    description = args.get("description", "")
    payment_description = args["payment_description"]
    deposit_to_account = args.get("deposit_to_account")

    accounts = await _get_all_accounts(client, bid)

    customer_id = None
    if customer_name:
        c = await client.request(GET_CUSTOMERS_LEGACY, {"businessId": bid})
        for cust in c["data"]["business"]["customers"]["edges"]:
            if cust["node"]["name"].lower() == customer_name.lower():
                customer_id = cust["node"]["id"]
                break

    context = f"{description} {payment_description}"
    income_id, income_name, score, explanation = find_best_account_match(
        income_category, accounts, "Income", context
    )
    if not income_id:
        return text("Error: No income accounts found")

    anchor_accounts = [
        a["node"] for a in accounts
        if a["node"]["type"]["name"] in ("Assets", "Liabilities & Credit Cards")
        and a["node"]["subtype"]["name"] in ("Cash & Bank", "Credit Card", "Loan and Line of Credit")
        and not a["node"]["isArchived"]
    ]
    if not anchor_accounts:
        return text("Error: No bank accounts found")

    anchor_id = anchor_name = None
    if deposit_to_account:
        for a in anchor_accounts:
            if a["name"].lower() == deposit_to_account.lower():
                anchor_id, anchor_name = a["id"], a["name"]
                break
        if not anchor_id:
            avail = "\n".join(f"- {a['name']}" for a in anchor_accounts)
            return text(f"❌ Deposit account '{deposit_to_account}' not found.\n\nAvailable:\n{avail}")
    if not anchor_id:
        anchor_id, anchor_name = anchor_accounts[0]["id"], anchor_accounts[0]["name"]

    line_item = {"accountId": income_id, "amount": float(amount), "balance": "INCREASE"}
    if customer_id:
        line_item["customerId"] = customer_id

    inp = {
        "businessId": bid,
        "externalId": f"income-{datetime.now().isoformat()}",
        "date": date,
        "description": description or payment_description,
        "anchor": {"accountId": anchor_id, "amount": float(amount), "direction": "DEPOSIT"},
        "lineItems": [line_item],
    }

    data = await client.request(CREATE_TX, {"input": inp})
    res = data["data"]["moneyTransactionCreate"]
    if not res.get("didSucceed"):
        errs = ", ".join(f"{e['path']}: {e['message']}" for e in res["inputErrors"])
        return text(f"❌ Failed to create income: {errs}")

    tid = res["transaction"]["id"]
    customer_text = f"- Customer: {customer_name}" + ("" if customer_id else " ⚠️ not in Wave")
    return text(
        f"✅ Created income transaction\n"
        f"- Amount: ${amount}\n"
        f"{customer_text if customer_name else '- Customer: (not specified)'}\n"
        f"- Date: {date}\n"
        f"- Deposited to: {anchor_name}\n"
        f"- Category: {income_category} → {income_name} ({score:.1%})\n"
        f"  💡 {explanation}\n"
        f"- Transaction ID: {tid}"
    )


async def _debug_accounts(client: WaveClient, args: dict) -> List[TextContent]:
    bid, err = need_business(client, args)
    if err:
        return err

    show_archived = args.get("show_archived", False)
    accounts = await _get_all_accounts(client, bid)

    by_type: dict = {}
    types_set: set = set()
    subtypes_set: set = set()
    for acc in accounts:
        node = acc["node"]
        if not show_archived and node["isArchived"]:
            continue
        t = node["type"]["name"]
        st = (node.get("subtype") or {}).get("name", "N/A")
        types_set.add(t)
        subtypes_set.add(st)
        by_type.setdefault(t, []).append({
            "name": node["name"],
            "subtype": st,
            "archived": node["isArchived"],
            "id": node["id"],
        })

    out = ["🔍 **Account Debug Information**", ""]
    out.append(f"- Total account types: {len(types_set)}")
    out.append(f"- Total subtypes: {len(subtypes_set)}")
    out.append(f"- Show archived: {show_archived}")
    out.append("")
    out.append(f"**Types:** {', '.join(sorted(types_set))}")
    out.append("")
    out.append(f"**Subtypes:** {', '.join(sorted(subtypes_set))}")
    out.append("")
    for t in sorted(by_type):
        accs = by_type[t]
        out.append(f"## {t} ({len(accs)} accounts)")
        for a in accs:
            flag = " 🗃️ ARCHIVED" if a["archived"] else ""
            out.append(f"- **{a['name']}**{flag}")
            out.append(f"  - Subtype: {a['subtype']}")
            out.append(f"  - ID: `{a['id']}`")
        out.append("")
    return text("\n".join(out))


async def _search_vendor(client: WaveClient, args: dict) -> List[TextContent]:
    bid, err = need_business(client, args)
    if err:
        return err
    name = args["vendor_name"]
    data = await client.request(GET_VENDORS_LEGACY, {"businessId": bid})
    for v in data["data"]["business"]["vendors"]["edges"]:
        if v["node"]["name"].lower() == name.lower():
            n = v["node"]
            return text(f"✅ Found vendor: **{n['name']}**\n- ID: `{n['id']}`\n- Email: {n['email'] or 'Not provided'}")
    return text(f"❌ Vendor '{name}' not found. Wave's API doesn't support vendor creation; add via the web UI.")


async def _search_customer(client: WaveClient, args: dict) -> List[TextContent]:
    bid, err = need_business(client, args)
    if err:
        return err
    name = args["customer_name"]
    data = await client.request(GET_CUSTOMERS_LEGACY, {"businessId": bid})
    for c in data["data"]["business"]["customers"]["edges"]:
        if c["node"]["name"].lower() == name.lower():
            n = c["node"]
            return text(f"✅ Found customer: **{n['name']}**\n- ID: `{n['id']}`\n- Email: {n['email'] or 'Not provided'}")
    return text(f"❌ Customer '{name}' not found. Use create_customer to add them.")


def tools():
    yield (
        Tool(
            name="create_expense_from_receipt",
            description=(
                "Legacy: create an expense by free-text category (uses fuzzy matching to "
                "pick the expense + bank accounts). For precise control prefer "
                "`create_money_transaction`."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "business_id": {"type": "string"},
                    "receipt_text": {"type": "string"},
                    "vendor_name": {"type": "string"},
                    "amount": {"type": "string"},
                    "date": {"type": "string"},
                    "category": {"type": "string", "default": "General Expenses"},
                    "description": {"type": "string"},
                    "payment_account": {"type": "string"},
                },
                "required": ["receipt_text", "amount", "date"],
            },
        ),
        _create_expense_from_receipt,
    )
    yield (
        Tool(
            name="create_income_from_payment",
            description=(
                "Legacy: create an income transaction by free-text category. "
                "For precise control prefer `create_money_transaction`."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "business_id": {"type": "string"},
                    "payment_description": {"type": "string"},
                    "customer_name": {"type": "string"},
                    "amount": {"type": "string"},
                    "date": {"type": "string"},
                    "income_category": {"type": "string", "default": "Sales"},
                    "description": {"type": "string"},
                    "deposit_to_account": {"type": "string"},
                },
                "required": ["payment_description", "amount", "date"],
            },
        ),
        _create_income_from_payment,
    )
    yield (
        Tool(
            name="debug_accounts",
            description="Dump every account grouped by type — useful for diagnosing categorization.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_id": {"type": "string"},
                    "show_archived": {"type": "boolean", "default": False},
                },
            },
        ),
        _debug_accounts,
    )
    yield (
        Tool(
            name="search_vendor",
            description="Legacy: case-insensitive vendor search by exact name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_id": {"type": "string"},
                    "vendor_name": {"type": "string"},
                },
                "required": ["vendor_name"],
            },
        ),
        _search_vendor,
    )
    yield (
        Tool(
            name="search_customer",
            description="Legacy: case-insensitive customer search by exact name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_id": {"type": "string"},
                    "customer_name": {"type": "string"},
                },
                "required": ["customer_name"],
            },
        ),
        _search_customer,
    )
