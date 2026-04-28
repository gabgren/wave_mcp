"""Reference / lookup tools: currencies, countries, user, oauth app."""

from __future__ import annotations

from typing import List

from mcp.types import TextContent, Tool

from wave_client import WaveClient

from ._common import json_text


CURRENT_USER = """
{ user { id firstName lastName defaultEmail createdAt } }
"""

OAUTH_APP = """
{ oAuthApplication { id name } }
"""

LIST_CURRENCIES = """
{ currencies { code symbol name plural exponent } }
"""

GET_CURRENCY = """
query($code: CurrencyCode!) {
  currency(code: $code) { code symbol name plural exponent }
}
"""

LIST_COUNTRIES = """
{ countries { code name nameWithArticle currency { code } } }
"""

GET_COUNTRY = """
query($code: CountryCode!) {
  country(code: $code) {
    code name nameWithArticle currency { code }
    provinces { code name slug }
  }
}
"""

GET_PROVINCE = """
query($code: ProvinceCode!) {
  province(code: $code) { code name slug }
}
"""


async def _user(client: WaveClient, _args: dict) -> List[TextContent]:
    data = await client.request(CURRENT_USER)
    return json_text(data["data"]["user"])


async def _oauth(client: WaveClient, _args: dict) -> List[TextContent]:
    data = await client.request(OAUTH_APP)
    return json_text(data["data"]["oAuthApplication"])


async def _currencies(client: WaveClient, _args: dict) -> List[TextContent]:
    data = await client.request(LIST_CURRENCIES)
    return json_text(data["data"]["currencies"])


async def _currency(client: WaveClient, args: dict) -> List[TextContent]:
    data = await client.request(GET_CURRENCY, {"code": args["code"]})
    return json_text(data["data"]["currency"])


async def _countries(client: WaveClient, _args: dict) -> List[TextContent]:
    data = await client.request(LIST_COUNTRIES)
    return json_text(data["data"]["countries"])


async def _country(client: WaveClient, args: dict) -> List[TextContent]:
    data = await client.request(GET_COUNTRY, {"code": args["code"]})
    return json_text(data["data"]["country"])


async def _province(client: WaveClient, args: dict) -> List[TextContent]:
    data = await client.request(GET_PROVINCE, {"code": args["code"]})
    return json_text(data["data"]["province"])


def tools():
    yield (
        Tool(
            name="get_current_user",
            description="Information about the currently authenticated Wave user.",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        _user,
    )
    yield (
        Tool(
            name="get_oauth_application",
            description="Metadata about the OAuth application this access token belongs to.",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        _oauth,
    )
    yield (
        Tool(
            name="list_currencies",
            description="List all currencies Wave supports.",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        _currencies,
    )
    yield (
        Tool(
            name="get_currency",
            description="Look up one currency by ISO code (e.g. USD, CAD).",
            inputSchema={
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "required": ["code"],
            },
        ),
        _currency,
    )
    yield (
        Tool(
            name="list_countries",
            description="List all countries Wave supports.",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        _countries,
    )
    yield (
        Tool(
            name="get_country",
            description="Country details, including its provinces/states.",
            inputSchema={
                "type": "object",
                "properties": {"code": {"type": "string", "description": "ISO 3166-1 alpha-2"}},
                "required": ["code"],
            },
        ),
        _country,
    )
    yield (
        Tool(
            name="get_province",
            description="Look up one province/state by Wave's province code (e.g. CA-QC).",
            inputSchema={
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "required": ["code"],
            },
        ),
        _province,
    )
