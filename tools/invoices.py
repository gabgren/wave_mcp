"""Invoice and invoice-payment tools (full lifecycle)."""

from __future__ import annotations

from typing import List

from mcp.types import TextContent, Tool

from errors import mutation_text, text
from wave_client import WaveClient

from ._common import json_text, need_business


INVOICE_FIELDS = """
id status title subhead
invoiceNumber poNumber invoiceDate dueDate
amountDue { value currency { code } }
amountPaid { value currency { code } }
total { value currency { code } }
exchangeRate
memo footer
disableAmexPayments disableCreditCardPayments disableBankPayments
viewUrl pdfUrl
createdAt modifiedAt
customer { id name email }
items {
  product { id name }
  description quantity
  unitPrice
  taxes { amount { value currency { code } } salesTax { id name rate } }
}
discounts {
  name
  ... on FixedInvoiceDiscount { amount }
  ... on PercentageInvoiceDiscount { percentage }
}
payments { id amount paymentMethod paymentDate memo paymentCurrency { code } }
"""

LIST_INVOICES = f"""
query(
  $businessId: ID!, $page: Int!, $pageSize: Int!, $sort: [InvoiceSort!]!,
  $status: InvoiceStatus, $customerId: ID, $currency: CurrencyCode,
  $invoiceDateStart: Date, $invoiceDateEnd: Date,
  $invoiceNumber: String, $amountDue: Decimal, $sourceId: ID,
  $modifiedAtAfter: DateTime, $modifiedAtBefore: DateTime
) {{
  business(id: $businessId) {{
    id
    invoices(
      page: $page, pageSize: $pageSize, sort: $sort,
      status: $status, customerId: $customerId, currency: $currency,
      invoiceDateStart: $invoiceDateStart, invoiceDateEnd: $invoiceDateEnd,
      invoiceNumber: $invoiceNumber, amountDue: $amountDue, sourceId: $sourceId,
      modifiedAtAfter: $modifiedAtAfter, modifiedAtBefore: $modifiedAtBefore
    ) {{
      pageInfo {{ currentPage totalPages totalCount }}
      edges {{ node {{ {INVOICE_FIELDS} }} }}
    }}
  }}
}}
"""

GET_INVOICE = f"""
query($businessId: ID!, $id: ID!) {{
  business(id: $businessId) {{ id invoice(id: $id) {{ {INVOICE_FIELDS} }} }}
}}
"""

CREATE_INVOICE = f"""
mutation($input: InvoiceCreateInput!) {{
  invoiceCreate(input: $input) {{
    didSucceed inputErrors {{ path message code }}
    invoice {{ {INVOICE_FIELDS} }}
  }}
}}
"""

PATCH_INVOICE = f"""
mutation($input: InvoicePatchInput!) {{
  invoicePatch(input: $input) {{
    didSucceed inputErrors {{ path message code }}
    invoice {{ {INVOICE_FIELDS} }}
  }}
}}
"""

CLONE_INVOICE = f"""
mutation($input: InvoiceCloneInput!) {{
  invoiceClone(input: $input) {{
    didSucceed inputErrors {{ path message code }}
    invoice {{ {INVOICE_FIELDS} }}
  }}
}}
"""

DELETE_INVOICE = """
mutation($input: InvoiceDeleteInput!) {
  invoiceDelete(input: $input) { didSucceed inputErrors { path message code } }
}
"""

APPROVE_INVOICE = f"""
mutation($input: InvoiceApproveInput!) {{
  invoiceApprove(input: $input) {{
    didSucceed inputErrors {{ path message code }}
    invoice {{ {INVOICE_FIELDS} }}
  }}
}}
"""

MARK_INVOICE_SENT = f"""
mutation($input: InvoiceMarkSentInput!) {{
  invoiceMarkSent(input: $input) {{
    didSucceed inputErrors {{ path message code }}
    invoice {{ {INVOICE_FIELDS} }}
  }}
}}
"""

SEND_INVOICE = f"""
mutation($input: InvoiceSendInput!) {{
  invoiceSend(input: $input) {{
    didSucceed inputErrors {{ path message code }}
    invoice {{ {INVOICE_FIELDS} }}
  }}
}}
"""

CREATE_INVOICE_PAYMENT = """
mutation($input: InvoicePaymentCreateManualInput!) {
  invoicePaymentCreateManual(input: $input) {
    didSucceed inputErrors { path message code }
    invoicePayment { id amount paymentMethod paymentDate memo paymentCurrency { code } }
  }
}
"""

PATCH_INVOICE_PAYMENT = """
mutation($input: InvoicePaymentPatchInput!) {
  invoicePaymentPatch(input: $input) {
    didSucceed inputErrors { path message code }
    invoicePayment { id amount paymentMethod paymentDate memo paymentCurrency { code } }
  }
}
"""

DELETE_INVOICE_PAYMENT = """
mutation($input: InvoicePaymentDeleteInput!) {
  invoicePaymentDelete(input: $input) { didSucceed inputErrors { path message code } }
}
"""

SEND_INVOICE_PAYMENT_RECEIPT = """
mutation($input: InvoicePaymentReceiptSendInput!) {
  invoicePaymentReceiptSend(input: $input) {
    didSucceed inputErrors { path message code }
  }
}
"""

GET_INVOICE_PAYMENT = """
query($businessId: ID!, $id: ID!) {
  business(id: $businessId) {
    id
    invoicePayment(id: $id) {
      id amount paymentMethod paymentDate memo paymentCurrency { code }
      invoice { id invoiceNumber }
    }
  }
}
"""

GET_INVOICE_ESTIMATE_SETTINGS = """
query($businessId: ID!) {
  business(id: $businessId) {
    id
    invoiceEstimateSettings {
      generalSettings { accentColor logoUrl }
    }
  }
}
"""


_INVOICE_INPUT = {
    "title": {"type": "string"},
    "subhead": {"type": "string"},
    "invoiceNumber": {"type": "string"},
    "poNumber": {"type": "string"},
    "invoiceDate": {"type": "string"},
    "dueDate": {"type": "string"},
    "currency": {"type": "string"},
    "exchangeRate": {"type": "number"},
    "memo": {"type": "string"},
    "footer": {"type": "string"},
    "disableAmexPayments": {"type": "boolean"},
    "disableCreditCardPayments": {"type": "boolean"},
    "disableBankPayments": {"type": "boolean"},
    "itemTitle": {"type": "string"},
    "unitTitle": {"type": "string"},
    "priceTitle": {"type": "string"},
    "amountTitle": {"type": "string"},
    "hideName": {"type": "boolean"},
    "hideDescription": {"type": "boolean"},
    "hideUnit": {"type": "boolean"},
    "hidePrice": {"type": "boolean"},
    "hideAmount": {"type": "boolean"},
    "requireTermsOfServiceAgreement": {"type": "boolean"},
    "items": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "productId": {"type": "string"},
                "description": {"type": "string"},
                "quantity": {"type": "number"},
                "unitPrice": {"type": "number"},
                "taxes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"salesTaxId": {"type": "string"}},
                        "required": ["salesTaxId"],
                    },
                },
            },
            "required": ["productId"],
        },
    },
    "discounts": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "discountType": {"type": "string", "enum": ["FIXED", "PERCENTAGE"]},
                "amount": {"type": "number"},
                "percentage": {"type": "number"},
            },
            "required": ["discountType"],
        },
    },
    "status": {"type": "string", "enum": ["DRAFT", "SAVED"]},
}


def _filter_input(args: dict, allowed: dict) -> dict:
    return {k: args[k] for k in allowed if args.get(k) is not None}


async def _list(client: WaveClient, args: dict) -> List[TextContent]:
    bid, err = need_business(client, args)
    if err:
        return err
    data = await client.request(
        LIST_INVOICES,
        {
            "businessId": bid,
            "page": args.get("page", 1),
            "pageSize": args.get("page_size", 25),
            "sort": args.get("sort") or ["INVOICE_DATE_DESC"],
            "status": args.get("status"),
            "customerId": args.get("customerId"),
            "currency": args.get("currency"),
            "invoiceDateStart": args.get("invoiceDateStart"),
            "invoiceDateEnd": args.get("invoiceDateEnd"),
            "invoiceNumber": args.get("invoiceNumber"),
            "amountDue": args.get("amountDue"),
            "sourceId": args.get("sourceId"),
            "modifiedAtAfter": args.get("modifiedAtAfter"),
            "modifiedAtBefore": args.get("modifiedAtBefore"),
        },
    )
    p = data["data"]["business"]["invoices"]
    return json_text({"pageInfo": p["pageInfo"], "invoices": [e["node"] for e in p["edges"]]})


async def _get(client: WaveClient, args: dict) -> List[TextContent]:
    bid, err = need_business(client, args)
    if err:
        return err
    data = await client.request(GET_INVOICE, {"businessId": bid, "id": args["invoice_id"]})
    return json_text(data["data"]["business"]["invoice"])


async def _create(client: WaveClient, args: dict) -> List[TextContent]:
    bid, err = need_business(client, args)
    if err:
        return err
    inp = _filter_input(args, _INVOICE_INPUT)
    inp["businessId"] = bid
    inp["customerId"] = args["customerId"]
    data = await client.request(CREATE_INVOICE, {"input": inp})
    res = data["data"]["invoiceCreate"]
    if res.get("didSucceed"):
        inv = res["invoice"]
        return text(f"✅ Created invoice {inv.get('invoiceNumber') or inv['id']} (ID: {inv['id']}, status: {inv['status']})")
    return mutation_text(res, "", failure_prefix="❌ invoiceCreate failed")


async def _patch(client: WaveClient, args: dict) -> List[TextContent]:
    inp = _filter_input(args, {**_INVOICE_INPUT, "customerId": True})
    inp["id"] = args["invoice_id"]
    data = await client.request(PATCH_INVOICE, {"input": inp})
    res = data["data"]["invoicePatch"]
    if res.get("didSucceed"):
        inv = res["invoice"]
        return text(f"✅ Patched invoice {inv.get('invoiceNumber') or inv['id']}")
    return mutation_text(res, "", failure_prefix="❌ invoicePatch failed")


async def _clone(client: WaveClient, args: dict) -> List[TextContent]:
    data = await client.request(CLONE_INVOICE, {"input": {"invoiceId": args["invoice_id"]}})
    res = data["data"]["invoiceClone"]
    if res.get("didSucceed"):
        inv = res["invoice"]
        return text(f"✅ Cloned invoice → {inv.get('invoiceNumber') or inv['id']}")
    return mutation_text(res, "", failure_prefix="❌ invoiceClone failed")


async def _delete(client: WaveClient, args: dict) -> List[TextContent]:
    data = await client.request(DELETE_INVOICE, {"input": {"invoiceId": args["invoice_id"]}})
    res = data["data"]["invoiceDelete"]
    return mutation_text(
        res,
        f"✅ Deleted invoice {args['invoice_id']}",
        failure_prefix="❌ invoiceDelete failed",
    )


async def _approve(client: WaveClient, args: dict) -> List[TextContent]:
    data = await client.request(APPROVE_INVOICE, {"input": {"invoiceId": args["invoice_id"]}})
    res = data["data"]["invoiceApprove"]
    if res.get("didSucceed"):
        inv = res["invoice"]
        return text(f"✅ Approved invoice {inv.get('invoiceNumber') or inv['id']}")
    return mutation_text(res, "", failure_prefix="❌ invoiceApprove failed")


async def _mark_sent(client: WaveClient, args: dict) -> List[TextContent]:
    inp = {"invoiceId": args["invoice_id"], "sendMethod": args["sendMethod"]}
    if args.get("sentAt"):
        inp["sentAt"] = args["sentAt"]
    data = await client.request(MARK_INVOICE_SENT, {"input": inp})
    res = data["data"]["invoiceMarkSent"]
    if res.get("didSucceed"):
        inv = res["invoice"]
        return text(f"✅ Marked sent: {inv.get('invoiceNumber') or inv['id']}")
    return mutation_text(res, "", failure_prefix="❌ invoiceMarkSent failed")


async def _send(client: WaveClient, args: dict) -> List[TextContent]:
    inp = {
        "invoiceId": args["invoice_id"],
        "to": args["to"],
        "attachPDF": args.get("attachPDF", True),
    }
    for k in ("subject", "message", "fromAddress", "ccMyself"):
        if args.get(k) is not None:
            inp[k] = args[k]
    data = await client.request(SEND_INVOICE, {"input": inp})
    res = data["data"]["invoiceSend"]
    if res.get("didSucceed"):
        return text(f"✅ Sent invoice {args['invoice_id']} to {', '.join(args['to'])}")
    return mutation_text(res, "", failure_prefix="❌ invoiceSend failed")


async def _record_payment(client: WaveClient, args: dict) -> List[TextContent]:
    inp = {
        "invoiceId": args["invoice_id"],
        "paymentAccountId": args["paymentAccountId"],
        "amount": args["amount"],
        "paymentDate": args["paymentDate"],
        "paymentMethod": args["paymentMethod"],
        "exchangeRate": args.get("exchangeRate", 1),
    }
    if args.get("memo") is not None:
        inp["memo"] = args["memo"]
    data = await client.request(CREATE_INVOICE_PAYMENT, {"input": inp})
    res = data["data"]["invoicePaymentCreateManual"]
    if res.get("didSucceed"):
        ip = res["invoicePayment"]
        cur = (ip.get("paymentCurrency") or {}).get("code") or ""
        return text(f"✅ Recorded payment {ip['id']} ({ip['amount']} {cur})")
    return mutation_text(res, "", failure_prefix="❌ invoicePaymentCreateManual failed")


async def _patch_payment(client: WaveClient, args: dict) -> List[TextContent]:
    inp = {"id": args["payment_id"]}
    for k in ("paymentAccountId", "amount", "paymentDate", "paymentMethod", "exchangeRate", "memo"):
        if args.get(k) is not None:
            inp[k] = args[k]
    data = await client.request(PATCH_INVOICE_PAYMENT, {"input": inp})
    res = data["data"]["invoicePaymentPatch"]
    if res.get("didSucceed"):
        return text(f"✅ Patched invoice payment {args['payment_id']}")
    return mutation_text(res, "", failure_prefix="❌ invoicePaymentPatch failed")


async def _delete_payment(client: WaveClient, args: dict) -> List[TextContent]:
    data = await client.request(DELETE_INVOICE_PAYMENT, {"input": {"id": args["payment_id"]}})
    res = data["data"]["invoicePaymentDelete"]
    return mutation_text(
        res,
        f"✅ Deleted invoice payment {args['payment_id']}",
        failure_prefix="❌ invoicePaymentDelete failed",
    )


async def _send_receipt(client: WaveClient, args: dict) -> List[TextContent]:
    inp = {
        "invoiceId": args["invoice_id"],
        "invoicePaymentId": args["payment_id"],
        "to": args["to"],
    }
    for k in ("message", "subject", "attachPdf", "ccMyself", "fromAddress"):
        if args.get(k) is not None:
            inp[k] = args[k]
    data = await client.request(SEND_INVOICE_PAYMENT_RECEIPT, {"input": inp})
    res = data["data"]["invoicePaymentReceiptSend"]
    return mutation_text(
        res,
        f"✅ Sent receipt to {', '.join(args['to'])}",
        failure_prefix="❌ invoicePaymentReceiptSend failed",
    )


async def _get_payment(client: WaveClient, args: dict) -> List[TextContent]:
    bid, err = need_business(client, args)
    if err:
        return err
    data = await client.request(GET_INVOICE_PAYMENT, {"businessId": bid, "id": args["payment_id"]})
    return json_text(data["data"]["business"]["invoicePayment"])


async def _settings(client: WaveClient, args: dict) -> List[TextContent]:
    bid, err = need_business(client, args)
    if err:
        return err
    data = await client.request(GET_INVOICE_ESTIMATE_SETTINGS, {"businessId": bid})
    return json_text(data["data"]["business"]["invoiceEstimateSettings"])


_INVOICE_SORT = {
    "type": "array",
    "items": {
        "type": "string",
        "enum": [
            "AMOUNT_DUE_ASC", "AMOUNT_DUE_DESC", "AMOUNT_PAID_ASC", "AMOUNT_PAID_DESC",
            "CREATED_AT_ASC", "CREATED_AT_DESC", "CUSTOMER_NAME_ASC", "CUSTOMER_NAME_DESC",
            "DUE_AT_ASC", "DUE_AT_DESC", "INVOICE_DATE_ASC", "INVOICE_DATE_DESC",
            "INVOICE_NUMBER_ASC", "INVOICE_NUMBER_DESC", "MODIFIED_AT_ASC", "MODIFIED_AT_DESC",
            "STATUS_ASC", "STATUS_DESC", "TOTAL_ASC", "TOTAL_DESC",
        ],
    },
    "default": ["INVOICE_DATE_DESC"],
}


def tools():
    yield (
        Tool(
            name="list_invoices",
            description="List invoices with rich filtering.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_id": {"type": "string"},
                    "page": {"type": "integer", "default": 1, "minimum": 1},
                    "page_size": {"type": "integer", "default": 25, "minimum": 1, "maximum": 200},
                    "sort": _INVOICE_SORT,
                    "status": {
                        "type": "string",
                        "enum": ["DRAFT", "OVERDUE", "OVERPAID", "PAID", "PARTIAL", "SAVED", "SENT", "UNPAID", "VIEWED"],
                    },
                    "customerId": {"type": "string"},
                    "currency": {"type": "string"},
                    "invoiceDateStart": {"type": "string"},
                    "invoiceDateEnd": {"type": "string"},
                    "invoiceNumber": {"type": "string"},
                    "amountDue": {"type": "number"},
                    "sourceId": {"type": "string"},
                    "modifiedAtAfter": {"type": "string"},
                    "modifiedAtBefore": {"type": "string"},
                },
            },
        ),
        _list,
    )
    yield (
        Tool(
            name="get_invoice",
            description="Fetch one invoice by ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_id": {"type": "string"},
                    "invoice_id": {"type": "string"},
                },
                "required": ["invoice_id"],
            },
        ),
        _get,
    )
    yield (
        Tool(
            name="create_invoice",
            description="Create an invoice.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_id": {"type": "string"},
                    "customerId": {"type": "string"},
                    **_INVOICE_INPUT,
                },
                "required": ["customerId"],
            },
        ),
        _create,
    )
    yield (
        Tool(
            name="patch_invoice",
            description="Patch an invoice. Only DRAFT/SAVED invoices can be modified.",
            inputSchema={
                "type": "object",
                "properties": {
                    "invoice_id": {"type": "string"},
                    "customerId": {"type": "string"},
                    **_INVOICE_INPUT,
                },
                "required": ["invoice_id"],
            },
        ),
        _patch,
    )
    yield (
        Tool(
            name="clone_invoice",
            description="Clone an existing invoice.",
            inputSchema={
                "type": "object",
                "properties": {"invoice_id": {"type": "string"}},
                "required": ["invoice_id"],
            },
        ),
        _clone,
    )
    yield (
        Tool(
            name="delete_invoice",
            description="Delete an invoice.",
            inputSchema={
                "type": "object",
                "properties": {"invoice_id": {"type": "string"}},
                "required": ["invoice_id"],
            },
        ),
        _delete,
    )
    yield (
        Tool(
            name="approve_invoice",
            description="Approve an invoice (DRAFT → SAVED).",
            inputSchema={
                "type": "object",
                "properties": {"invoice_id": {"type": "string"}},
                "required": ["invoice_id"],
            },
        ),
        _approve,
    )
    yield (
        Tool(
            name="mark_invoice_sent",
            description="Mark an invoice as sent (without actually emailing).",
            inputSchema={
                "type": "object",
                "properties": {
                    "invoice_id": {"type": "string"},
                    "sendMethod": {
                        "type": "string",
                        "enum": ["EXPORT_PDF", "GMAIL", "MARKED_SENT", "NOT_SENT", "OUTLOOK", "SHARED_LINK", "SKIPPED", "WAVE", "YAHOO"],
                    },
                    "sentAt": {"type": "string", "description": "ISO datetime"},
                },
                "required": ["invoice_id", "sendMethod"],
            },
        ),
        _mark_sent,
    )
    yield (
        Tool(
            name="send_invoice",
            description="Send an invoice via Wave's email. Requires the business to have email sending enabled.",
            inputSchema={
                "type": "object",
                "properties": {
                    "invoice_id": {"type": "string"},
                    "to": {"type": "array", "items": {"type": "string"}},
                    "subject": {"type": "string"},
                    "message": {"type": "string"},
                    "attachPDF": {"type": "boolean", "default": True},
                    "fromAddress": {"type": "string"},
                    "ccMyself": {"type": "boolean"},
                },
                "required": ["invoice_id", "to"],
            },
        ),
        _send,
    )
    yield (
        Tool(
            name="record_invoice_payment",
            description="Record a manual payment against an invoice.",
            inputSchema={
                "type": "object",
                "properties": {
                    "invoice_id": {"type": "string"},
                    "paymentAccountId": {"type": "string"},
                    "amount": {"type": "number"},
                    "paymentDate": {"type": "string"},
                    "paymentMethod": {
                        "type": "string",
                        "enum": ["BANK_TRANSFER", "CASH", "CHEQUE", "CREDIT_CARD", "OTHER", "PAYPAL", "UNSPECIFIED"],
                    },
                    "exchangeRate": {"type": "number", "default": 1},
                    "memo": {"type": "string"},
                },
                "required": ["invoice_id", "paymentAccountId", "amount", "paymentDate", "paymentMethod"],
            },
        ),
        _record_payment,
    )
    yield (
        Tool(
            name="patch_invoice_payment",
            description="Patch an invoice payment.",
            inputSchema={
                "type": "object",
                "properties": {
                    "payment_id": {"type": "string"},
                    "paymentAccountId": {"type": "string"},
                    "amount": {"type": "number"},
                    "paymentDate": {"type": "string"},
                    "paymentMethod": {"type": "string"},
                    "exchangeRate": {"type": "number"},
                    "memo": {"type": "string"},
                },
                "required": ["payment_id"],
            },
        ),
        _patch_payment,
    )
    yield (
        Tool(
            name="delete_invoice_payment",
            description="Delete an invoice payment.",
            inputSchema={
                "type": "object",
                "properties": {"payment_id": {"type": "string"}},
                "required": ["payment_id"],
            },
        ),
        _delete_payment,
    )
    yield (
        Tool(
            name="send_invoice_payment_receipt",
            description="Email a payment receipt to the customer.",
            inputSchema={
                "type": "object",
                "properties": {
                    "invoice_id": {"type": "string"},
                    "payment_id": {"type": "string"},
                    "to": {"type": "array", "items": {"type": "string"}},
                    "subject": {"type": "string"},
                    "message": {"type": "string"},
                    "attachPdf": {"type": "boolean"},
                    "fromAddress": {"type": "string"},
                    "ccMyself": {"type": "boolean"},
                },
                "required": ["invoice_id", "payment_id", "to"],
            },
        ),
        _send_receipt,
    )
    yield (
        Tool(
            name="get_invoice_payment",
            description="Fetch one invoice payment by ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "business_id": {"type": "string"},
                    "payment_id": {"type": "string"},
                },
                "required": ["payment_id"],
            },
        ),
        _get_payment,
    )
    yield (
        Tool(
            name="get_invoice_estimate_settings",
            description="Get the business's invoice/estimate display settings.",
            inputSchema={
                "type": "object",
                "properties": {"business_id": {"type": "string"}},
            },
        ),
        _settings,
    )
