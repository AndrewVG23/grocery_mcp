"""Public listing pages and MCP server card for directory scanners."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from grocery_mcp.config import public_base_url

DEFAULT_HOST = "https://grocery-mcp-production.up.railway.app"
SERVER_VERSION = "0.1.1"
CONTACT = "vangilder.andrew@gmail.com"


def public_host() -> str:
    return public_base_url() or DEFAULT_HOST


def _page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body {{ font-family: system-ui, sans-serif; max-width: 40rem; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }}
a {{ color: #1a365d; }}
code {{ font-size: 0.95em; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def register_directory_pages(mcp) -> None:
    host = public_host()

    @mcp.custom_route("/listing/docs", methods=["GET"])
    async def listing_docs(_: Request) -> HTMLResponse:
        body = _page(
            "Grocery MCP",
            f"""<h1>Grocery MCP</h1>
<p>Version {SERVER_VERSION}. Streamable HTTP at <a href="{host}/mcp">{host}/mcp</a>.</p>
<p>Search Kettle Range and Outpost storefronts and return direct product links. The shopper opens links and checks out on the retailer site. <code>cart_prefilled</code> is always false.</p>
<p>OAuth with dynamic client registration is enabled on the hosted deployment. Claude and ChatGPT connectors should use OAuth.</p>
<p>Questions: <a href="mailto:{CONTACT}">{CONTACT}</a>.</p>""",
        )
        return HTMLResponse(body)

    @mcp.custom_route("/listing/privacy", methods=["GET"])
    async def listing_privacy(_: Request) -> HTMLResponse:
        body = _page(
            "Privacy",
            f"""<h1>Privacy</h1>
<p>Grocery MCP does not complete purchases or store retailer passwords. Product links and prices come from each retailer's public storefront at request time. OAuth client registrations may be stored when a database is configured.</p>
<p>Contact: <a href="mailto:{CONTACT}">{CONTACT}</a>.</p>""",
        )
        return HTMLResponse(body)

    @mcp.custom_route("/.well-known/mcp/server-card.json", methods=["GET"])
    async def server_card(_: Request) -> JSONResponse:
        return JSONResponse(
            {
                "serverInfo": {
                    "name": "grocery",
                    "title": "Grocery MCP",
                    "version": SERVER_VERSION,
                    "documentation": f"{host}/listing/docs",
                },
                "description": "Search direct grocery storefronts and create product-link pickup handoffs.",
                "documentation": f"{host}/listing/docs",
                "transport": {"type": "streamable-http", "url": f"{host}/mcp"},
                "authentication": {
                    "required": True,
                    "schemes": ["oauth2"],
                },
                "privacy": f"{host}/listing/privacy",
            }
        )

    @mcp.custom_route("/.well-known/glama.json", methods=["GET"])
    async def glama_manifest(_: Request) -> JSONResponse:
        return JSONResponse(
            {
                "$schema": "https://glama.ai/mcp/schemas/server.json",
                "maintainers": ["AndrewVG23"],
            }
        )
