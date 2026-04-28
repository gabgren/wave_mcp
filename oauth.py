"""One-time OAuth bootstrap for Wave: opens browser, captures the auth code on
a local listener, exchanges it for tokens, and writes them to .env."""

from __future__ import annotations

import logging
import os
import re
import secrets
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Callable, Dict, Optional

import httpx

logger = logging.getLogger("wave-mcp-server.oauth")

WAVE_AUTHORIZE_URL = "https://api.waveapps.com/oauth2/authorize/"
WAVE_TOKEN_URL = "https://api.waveapps.com/oauth2/token/"

DEFAULT_OAUTH_SCOPES = [
    "account:read",
    "account:write",
    "business:read",
    "customer:read",
    "customer:write",
    "invoice:read",
    "invoice:write",
    "product:read",
    "product:write",
    "user.application.transactions:read",
    "user.application.transactions:write",
    "user.profile:read",
    "vendor:read",
    "vendor:write",
]


def persist_tokens_to_env(env_path: Path) -> Callable[[str, str], None]:
    """Return a callback that writes refreshed access/refresh tokens to a .env file."""

    def _persist(access_token: str, refresh_token: Optional[str]) -> None:
        try:
            text = env_path.read_text() if env_path.exists() else ""
        except Exception as e:
            logger.error(f"Could not read {env_path} for token persistence: {e}")
            return

        def _set(key: str, value: str, body: str) -> str:
            pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
            line = f"{key}={value}"
            if pattern.search(body):
                return pattern.sub(line, body)
            if body and not body.endswith("\n"):
                body += "\n"
            return body + line + "\n"

        text = _set("WAVE_ACCESS_TOKEN", access_token, text)
        if refresh_token:
            text = _set("WAVE_REFRESH_TOKEN", refresh_token, text)

        try:
            env_path.write_text(text)
            logger.info(f"Persisted refreshed Wave tokens to {env_path}")
        except Exception as e:
            logger.error(f"Could not write refreshed tokens to {env_path}: {e}")

    return _persist


def run_oauth_bootstrap(redirect_uri: str) -> int:
    client_id = os.getenv("WAVE_CLIENT_ID")
    client_secret = os.getenv("WAVE_CLIENT_SECRET")
    if not client_id or not client_secret:
        print(
            "ERROR: WAVE_CLIENT_ID and WAVE_CLIENT_SECRET must be set in your "
            ".env (or environment) before running --auth.",
            file=sys.stderr,
        )
        return 1

    parsed_redirect = urllib.parse.urlparse(redirect_uri)
    if parsed_redirect.hostname not in ("localhost", "127.0.0.1"):
        print(
            f"ERROR: redirect_uri must point to localhost (got {redirect_uri}).",
            file=sys.stderr,
        )
        return 1
    port = parsed_redirect.port or (443 if parsed_redirect.scheme == "https" else 80)
    redirect_path = parsed_redirect.path or "/"

    state = secrets.token_urlsafe(24)
    authorize_url = f"{WAVE_AUTHORIZE_URL}?" + urllib.parse.urlencode({
        "client_id": client_id,
        "response_type": "code",
        "scope": " ".join(DEFAULT_OAUTH_SCOPES),
        "redirect_uri": redirect_uri,
        "state": state,
    })

    captured: Dict[str, Optional[str]] = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def log_message(self, *_args, **_kwargs):
            return

        def _send_html(self, status: int, body: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != redirect_path:
                self._send_html(404, "<h1>Not found</h1>")
                return

            qs = urllib.parse.parse_qs(parsed.query)
            captured["code"] = (qs.get("code") or [None])[0]
            captured["state"] = (qs.get("state") or [None])[0]
            captured["error"] = (qs.get("error") or [None])[0]
            captured["error_description"] = (qs.get("error_description") or [None])[0]

            if captured["error"]:
                body = (
                    "<h1>Wave authorization failed</h1>"
                    f"<p><b>{captured['error']}</b>: "
                    f"{captured.get('error_description') or ''}</p>"
                )
            elif not captured["code"]:
                body = "<h1>No authorization code received</h1>"
            else:
                body = (
                    "<h1>Wave authorization complete</h1>"
                    "<p>You can close this tab and return to your terminal.</p>"
                )
            self._send_html(200, body)

    try:
        httpd = HTTPServer(("127.0.0.1", port), CallbackHandler)
    except OSError as e:
        print(f"ERROR: Could not bind to port {port}: {e}", file=sys.stderr)
        print(
            "       Pick a different port with --redirect-uri "
            "http://localhost:<port>/callback (and register it in Wave).",
            file=sys.stderr,
        )
        return 1

    print(f"Listening for Wave OAuth callback on {redirect_uri}")
    print(f"Opening browser to: {authorize_url}")
    print(
        "If the browser does not open automatically, copy the URL above into "
        "your browser. Press Ctrl+C to abort."
    )
    try:
        webbrowser.open(authorize_url)
    except Exception:
        pass

    try:
        while not captured:
            httpd.handle_request()
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        httpd.server_close()
        return 1
    httpd.server_close()

    if captured.get("error"):
        print(
            f"ERROR: Wave returned {captured['error']}: "
            f"{captured.get('error_description') or ''}",
            file=sys.stderr,
        )
        return 1
    if captured.get("state") != state:
        print("ERROR: State mismatch — possible CSRF, aborting.", file=sys.stderr)
        return 1
    code = captured.get("code")
    if not code:
        print("ERROR: No authorization code received.", file=sys.stderr)
        return 1

    print("Authorization code received, exchanging for tokens...")
    try:
        response = httpx.post(
            WAVE_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
            },
            timeout=30.0,
        )
    except httpx.HTTPError as e:
        print(f"ERROR: Token exchange request failed: {e}", file=sys.stderr)
        return 1

    if response.status_code != 200:
        print(
            f"ERROR: Token exchange failed: {response.status_code} {response.text}",
            file=sys.stderr,
        )
        return 1

    tokens = response.json()
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    if not access_token or not refresh_token:
        print(
            f"ERROR: Token response missing access_token or refresh_token: {tokens}",
            file=sys.stderr,
        )
        return 1

    env_path = Path(__file__).resolve().parent / ".env"
    persist_tokens_to_env(env_path)(access_token, refresh_token)

    print(f"✓ Wrote WAVE_ACCESS_TOKEN and WAVE_REFRESH_TOKEN to {env_path}")
    print("You can now start the MCP server normally.")
    return 0
