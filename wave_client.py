"""Wave GraphQL client with automatic OAuth refresh and concurrency limiting."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, Optional

import httpx

logger = logging.getLogger("wave-mcp-server.client")


class WaveClient:
    """Async client for Wave's public GraphQL API.

    - Sends queries to https://gql.waveapps.com/graphql/public
    - Retries once on 401 by exchanging a refresh token via OAuth
    - Persists rotated tokens via on_token_refresh callback
    - Limits concurrency to 2 simultaneous requests (Wave rate limit)
    """

    def __init__(
        self,
        access_token: str,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        refresh_token: Optional[str] = None,
        on_token_refresh: Optional[Callable[[str, str], None]] = None,
    ):
        self.access_token = access_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.on_token_refresh = on_token_refresh
        self.base_url = "https://gql.waveapps.com/graphql/public"
        self.token_url = "https://api.waveapps.com/oauth2/token/"
        self.business_id: Optional[str] = None
        self._refresh_lock = asyncio.Lock()
        self._concurrency = asyncio.Semaphore(2)

    @property
    def can_refresh(self) -> bool:
        return all([self.client_id, self.client_secret, self.refresh_token])

    async def refresh_access_token(self) -> bool:
        if not self.can_refresh:
            logger.warning(
                "Cannot refresh Wave access token: missing client_id, client_secret, or refresh_token"
            )
            return False

        async with self._refresh_lock:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.token_url,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": self.refresh_token,
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                    },
                    timeout=30.0,
                )

            if response.status_code != 200:
                logger.error(f"Token refresh failed: {response.status_code} {response.text}")
                return False

            data = response.json()
            self.access_token = data["access_token"]
            if data.get("refresh_token"):
                self.refresh_token = data["refresh_token"]

            logger.info("Successfully refreshed Wave access token")
            if self.on_token_refresh:
                try:
                    self.on_token_refresh(self.access_token, self.refresh_token)
                except Exception as e:
                    logger.error(f"Token persistence callback failed: {e}")
            return True

    async def request(self, query: str, variables: Optional[Dict] = None) -> Dict[str, Any]:
        """Execute a GraphQL request, refreshing on 401 once."""
        payload = {"query": query, "variables": variables or {}}

        async def _post() -> httpx.Response:
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }
            async with httpx.AsyncClient() as client:
                return await client.post(
                    self.base_url,
                    headers=headers,
                    json=payload,
                    timeout=30.0,
                )

        async with self._concurrency:
            response = await _post()

            if response.status_code == 401 and self.can_refresh:
                logger.info("Wave returned 401; attempting token refresh")
                if await self.refresh_access_token():
                    response = await _post()

            if response.status_code != 200:
                logger.error(f"API Error: {response.status_code}")
                logger.error(f"Response: {response.text}")

            response.raise_for_status()
            data = response.json()

            if "errors" in data and data["errors"]:
                # Surface GraphQL errors clearly; callers may inspect data anyway.
                first = data["errors"][0]
                msg = first.get("message", "Unknown GraphQL error")
                raise WaveGraphQLError(msg, data["errors"])

            return data

    # Backward-compat shim for any code still calling _make_request
    async def _make_request(self, query: str, variables: Optional[Dict] = None) -> Dict[str, Any]:
        return await self.request(query, variables)


class WaveGraphQLError(Exception):
    """Raised when Wave returns a GraphQL `errors[]` payload."""

    def __init__(self, message: str, errors: list):
        super().__init__(message)
        self.errors = errors
