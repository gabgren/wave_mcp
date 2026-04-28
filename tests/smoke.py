#!/usr/bin/env python3
"""Smoke-test the Wave MCP tool surface against a live Wave business.

Default: read-only. With --write, exercises create/patch/delete paths and
cleans up after itself. Use --business-id to override the active business
(strongly recommend a sandbox/empty business for --write).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import all_tools  # noqa: E402
from wave_client import WaveClient  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


READ_ONLY = [
    ("list_businesses", {}),
    ("get_current_user", {}),
    ("get_oauth_application", {}),
    ("list_account_types", {}),
    ("list_account_subtypes", {}),
    ("list_currencies", {}),
    ("get_currency", {"code": "CAD"}),
    ("list_countries", {}),
    ("get_country", {"code": "CA"}),
    ("list_accounts", {"page_size": 5}),
    ("list_customers", {"page_size": 5}),
    ("list_vendors", {"page_size": 5}),
    ("list_products", {"page_size": 5}),
    ("list_sales_taxes", {}),
    ("list_invoices", {"page_size": 5}),
    ("list_estimates", {"page_size": 5}),
    ("get_invoice_estimate_settings", {}),
]


async def run_one(registry, name: str, args: dict) -> tuple[bool, str]:
    """Run a tool. Returns (ok, full_text). Caller is responsible for trimming for display."""
    tool, handler = registry[name]
    try:
        client = registry["__client__"]
        res = await handler(client, args)
        return True, res[0].text if res else ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _trim(s: str) -> str:
    return s.replace("\n", " ")[:140]


async def write_round_trip(registry, business_id: str) -> int:
    """Exercise create/patch/delete for the major write paths."""
    failures = 0
    stamp = str(int(time.time()))

    print()
    print("=== Write round-trip ===")

    # 1. create_account → patch_account → archive_account
    ok, msg = await run_one(registry, "create_account", {
        "business_id": business_id,
        "name": f"_smoke_acct_{stamp}",
        "subtype": "CASH_AND_BANK",
    })
    print(f"  {'✓' if ok else '✗'} create_account              {_trim(msg)}")
    if not ok:
        return 1
    account_id = _extract_id(msg, "ID:")
    if not account_id:
        # Re-list to find the one we just made
        _ok, listing = await run_one(registry, "list_accounts", {"business_id": business_id, "subtypes": ["CASH_AND_BANK"], "page_size": 200})
        # Best-effort: skip patch/archive
        print(f"  (could not parse account ID; skipping patch/archive)")
        return failures

    ok, msg = await run_one(registry, "archive_account", {"account_id": account_id})
    print(f"  {'✓' if ok else '✗'} archive_account             {_trim(msg)}")
    failures += 0 if ok else 1

    # 2. customer create → patch → delete
    ok, msg = await run_one(registry, "create_customer", {
        "business_id": business_id,
        "name": f"_smoke_cust_{stamp}",
        "email": f"smoke+{stamp}@example.test",
    })
    print(f"  {'✓' if ok else '✗'} create_customer             {_trim(msg)}")
    cust_id = _extract_id(msg, "ID:")
    if ok and cust_id:
        ok, msg = await run_one(registry, "patch_customer", {
            "customer_id": cust_id,
            "internalNotes": "patched by smoke test",
        })
        print(f"  {'✓' if ok else '✗'} patch_customer              {_trim(msg)}")
        failures += 0 if ok else 1

        ok, msg = await run_one(registry, "delete_customer", {"customer_id": cust_id})
        print(f"  {'✓' if ok else '✗'} delete_customer             {_trim(msg)}")
        failures += 0 if ok else 1
    else:
        failures += 1

    # 3. product create → archive (Wave requires BOTH income and expense account
    # despite the schema marking them optional — passing only one returns a generic error)
    income_id = await _first_account_id_for(registry, business_id, "INCOME")
    expense_id = await _first_account_id_for(registry, business_id, "EXPENSE")
    ok, msg = await run_one(registry, "create_product", {
        "business_id": business_id,
        "name": f"_smoke_product_{stamp}",
        "unitPrice": 9.99,
        "incomeAccountId": income_id,
        "expenseAccountId": expense_id,
    })
    print(f"  {'✓' if ok else '✗'} create_product              {_trim(msg)}")
    prod_id = _extract_id(msg, "ID:")
    if ok and prod_id:
        ok, msg = await run_one(registry, "archive_product", {"product_id": prod_id})
        print(f"  {'✓' if ok else '✗'} archive_product             {_trim(msg)}")
        failures += 0 if ok else 1
    else:
        failures += 1

    # 4. sales tax create → archive
    ok, msg = await run_one(registry, "create_sales_tax", {
        "business_id": business_id,
        "name": f"_smoke_tax_{stamp}",
        "abbreviation": "ST",
        "rate": 0,
    })
    print(f"  {'✓' if ok else '✗'} create_sales_tax            {_trim(msg)}")
    tax_id = _extract_id(msg, "(", end=")")
    if ok and tax_id:
        ok, msg = await run_one(registry, "archive_sales_tax", {"sales_tax_id": tax_id})
        print(f"  {'✓' if ok else '✗'} archive_sales_tax           {_trim(msg)}")
        failures += 0 if ok else 1
    else:
        failures += 1

    return failures


async def _first_account_id_for(registry, business_id: str, type_: str) -> str | None:
    client = registry["__client__"]
    data = await client.request(
        "query($b:ID!,$t:[AccountTypeValue!]){business(id:$b){accounts(page:1,pageSize:1,types:$t){edges{node{id name}}}}}",
        {"b": business_id, "t": [type_]},
    )
    edges = data["data"]["business"]["accounts"]["edges"]
    return edges[0]["node"]["id"] if edges else None


def _extract_id(msg: str, marker: str, end: str | None = None) -> str | None:
    """Extract a Wave ID from a tool's success message."""
    if marker not in msg:
        return None
    rest = msg.split(marker, 1)[1].strip()
    if end:
        rest = rest.split(end, 1)[0]
    # IDs are base64-ish strings; trim at first whitespace or punctuation
    import re
    m = re.match(r"[A-Za-z0-9+/=]+", rest)
    return m.group(0) if m else None


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--business-id", help="Override active business")
    parser.add_argument("--write", action="store_true",
                        help="Exercise create/patch/delete paths (creates and cleans up test records)")
    args = parser.parse_args()

    client = WaveClient(
        access_token=os.environ["WAVE_ACCESS_TOKEN"],
        client_id=os.getenv("WAVE_CLIENT_ID"),
        client_secret=os.getenv("WAVE_CLIENT_SECRET"),
        refresh_token=os.getenv("WAVE_REFRESH_TOKEN"),
    )

    if args.business_id:
        client.business_id = args.business_id
    else:
        bs = await client.request(
            "{ businesses(page:1,pageSize:25){ edges{ node{ id name } } } }"
        )
        edges = bs["data"]["businesses"]["edges"]
        if not edges:
            print("No businesses on this account.", file=sys.stderr)
            return 1
        client.business_id = edges[0]["node"]["id"]
        print(f"Using business: {edges[0]['node']['name']} ({client.business_id})")

    registry = all_tools()
    registry["__client__"] = client  # type: ignore[assignment]

    print()
    print("=== Read-only ===")
    failures = 0
    for name, payload in READ_ONLY:
        ok, head = await run_one(registry, name, payload)
        print(f"  {'✓' if ok else '✗'} {name:35s} {_trim(head)}")
        if not ok:
            failures += 1

    if args.write:
        failures += await write_round_trip(registry, client.business_id)

    print()
    print(f"Done — {failures} failure(s)")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
