#!/usr/bin/env python3
"""Wave Accounting MCP Server — entry point.

Run normally: `python mcp_server.py`
Bootstrap OAuth (one-time): `python mcp_server.py --auth`
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env next to this script so the working directory doesn't matter
# (Claude Desktop / Claude Code launch this from arbitrary CWDs).
load_dotenv(Path(__file__).resolve().parent / ".env")

# Make `tools.*` importable regardless of how the file is launched.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server import Server  # noqa: E402
from mcp.server.models import InitializationOptions  # noqa: E402
from mcp.types import Resource, TextContent  # noqa: E402

from oauth import persist_tokens_to_env, run_oauth_bootstrap  # noqa: E402
from tools import all_tools  # noqa: E402
from wave_client import WaveClient  # noqa: E402


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("wave-mcp-server")

wave_client: WaveClient | None = None
TOOLS: dict = {}

app = Server("wave-accounting")


@app.list_tools()
async def handle_list_tools():
    return [tool for (tool, _handler) in TOOLS.values()]


@app.call_tool()
async def handle_call_tool(name: str, arguments: dict):
    if not wave_client:
        return [TextContent(
            type="text",
            text="Error: Wave client not initialized. Check WAVE_ACCESS_TOKEN.",
        )]
    entry = TOOLS.get(name)
    if not entry:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    _tool, handler = entry
    try:
        return await handler(wave_client, arguments or {})
    except Exception as e:
        logger.exception(f"Error in tool {name}")
        return [TextContent(type="text", text=f"Error: {e}")]


# Light resource layer kept for backward compatibility.
@app.list_resources()
async def handle_list_resources():
    return [
        Resource(uri="wave://businesses", name="Wave Businesses",
                 description="Information about your Wave businesses",
                 mimeType="application/json"),
        Resource(uri="wave://accounts", name="Chart of Accounts",
                 description="Your business chart of accounts",
                 mimeType="application/json"),
    ]


@app.read_resource()
async def handle_read_resource(uri: str):
    import json
    if not wave_client:
        raise RuntimeError("Wave client not initialized")
    if uri == "wave://businesses":
        data = await wave_client.request(
            "{ businesses(page:1,pageSize:50){ edges{ node{ id name isArchived } } } }"
        )
        return json.dumps(data["data"], indent=2)
    if uri == "wave://accounts":
        if not wave_client.business_id:
            raise RuntimeError("Business ID not set")
        data = await wave_client.request(
            """query($id:ID!){ business(id:$id){
                accounts(page:1,pageSize:200){
                  edges{ node{ id name displayId isArchived
                    type{ name normalBalanceType } subtype{ name }
                  } } } } }""",
            {"id": wave_client.business_id},
        )
        return json.dumps(data["data"], indent=2)
    raise ValueError(f"Unknown resource: {uri}")


async def main():
    global wave_client, TOOLS

    access_token = os.getenv("WAVE_ACCESS_TOKEN")
    if not access_token:
        logger.error("WAVE_ACCESS_TOKEN environment variable is required")
        return

    client_id = os.getenv("WAVE_CLIENT_ID")
    client_secret = os.getenv("WAVE_CLIENT_SECRET")
    refresh_token = os.getenv("WAVE_REFRESH_TOKEN")

    env_path = Path(__file__).resolve().parent / ".env"
    on_token_refresh = (
        persist_tokens_to_env(env_path)
        if all([client_id, client_secret, refresh_token])
        else None
    )

    if on_token_refresh:
        logger.info("OAuth refresh enabled — access tokens will renew automatically")
    else:
        logger.info(
            "OAuth refresh disabled — set WAVE_CLIENT_ID, WAVE_CLIENT_SECRET, "
            "and WAVE_REFRESH_TOKEN to enable automatic access-token renewal"
        )

    wave_client = WaveClient(
        access_token=access_token,
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
        on_token_refresh=on_token_refresh,
    )

    business_id = os.getenv("WAVE_BUSINESS_ID")
    if business_id:
        wave_client.business_id = business_id
        logger.info(f"Using business ID: {business_id}")

    TOOLS = all_tools()
    logger.info(f"Registered {len(TOOLS)} tools")

    # Auto-select if there's only one business.
    try:
        data = await wave_client.request(
            "{ businesses(page:1,pageSize:25){ edges{ node{ id name } } } }"
        )
        edges = data["data"]["businesses"]["edges"]
        logger.info(f"Connected to Wave API. Found {len(edges)} businesses.")
        if not wave_client.business_id and len(edges) == 1:
            wave_client.business_id = edges[0]["node"]["id"]
            logger.info(f"Auto-selected business: {edges[0]['node']['name']} ({wave_client.business_id})")
    except Exception as e:
        logger.error(f"Failed to connect to Wave API: {e}")
        return

    from mcp.server.stdio import stdio_server
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="wave-accounting",
                server_version="2.0.0",
                capabilities=app.get_capabilities(
                    notification_options=type("NotificationOptions", (), {
                        "resources_changed": False,
                        "tools_changed": False,
                        "prompts_changed": False,
                    })(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wave Accounting MCP server")
    parser.add_argument(
        "--auth",
        action="store_true",
        help="Run a one-time interactive OAuth bootstrap to obtain access + "
             "refresh tokens and write them to .env, then exit.",
    )
    parser.add_argument(
        "--redirect-uri",
        default="http://localhost:8765/callback",
        help="OAuth redirect URI (must be registered in your Wave Developer App).",
    )
    args = parser.parse_args()

    if args.auth:
        sys.exit(run_oauth_bootstrap(args.redirect_uri))

    asyncio.run(main())
