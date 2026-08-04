"""OAuth setup for hosted MCP deployments."""
from __future__ import annotations

from fastmcp.server.auth.providers.in_memory import InMemoryOAuthProvider
from mcp.server.auth.settings import ClientRegistrationOptions
from mcp.shared.auth import OAuthClientInformationFull

from grocery_mcp.config import mcp_auth_enabled, public_base_url
from grocery_mcp.database import database_url, get_state, put_state


class PersistentClientOAuthProvider(InMemoryOAuthProvider):
    """FastMCP's local OAuth flow with durable dynamic client registrations."""

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        client = await super().get_client(client_id)
        if client is not None or not database_url():
            return client
        payload = await get_state("client", client_id)
        if payload is None:
            return None
        client = OAuthClientInformationFull.model_validate(payload)
        self.clients[client_id] = client
        return client

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        await super().register_client(client_info)
        if database_url() and client_info.client_id:
            await put_state(
                "client",
                client_info.client_id,
                client_info.model_dump(mode="json"),
            )


def build_http_auth():
    """Enable OAuth DCR only when the service has a public base URL."""
    if not mcp_auth_enabled():
        return None
    base_url = public_base_url()
    if not base_url:
        return None

    provider_type = PersistentClientOAuthProvider if database_url() else InMemoryOAuthProvider
    return provider_type(
        base_url=base_url,
        client_registration_options=ClientRegistrationOptions(enabled=True),
    )
