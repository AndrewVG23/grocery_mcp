"""Public listing pages and MCP server card for directory scanners."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

from grocery_mcp.config import public_base_url
from grocery_mcp.outpost_checkout import (
    load_outpost_cart,
    plan_json,
    plan_url_for,
    render_outpost_cart_page,
)

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
<p>Search Kettle Range and Outpost. <code>start_grocery_checkout</code> starts a cart the shopper pays for on the store site. Kettle Range returns the store checkout link. Outpost opens a browser window with the cart already filled. The shopper can sign in to Outpost in that window. This service does not take a card number or the Outpost password.</p>
<p>OAuth with dynamic client registration is enabled on the hosted deployment. Claude and ChatGPT connectors should use OAuth.</p>
<p>Questions: <a href="mailto:{CONTACT}">{CONTACT}</a>.</p>""",
        )
        return HTMLResponse(body)

    @mcp.custom_route("/listing/privacy", methods=["GET"])
    async def listing_privacy(_: Request) -> HTMLResponse:
        body = _page(
            "Privacy",
            f"""<h1>Privacy</h1>
<p>Grocery MCP does not take card numbers or store retailer passwords. A Kettle Range checkout link is a guest session for that cart. An Outpost checkout opens a local browser window with the cart already filled. Signing in on that window stays on this Mac for the next cart. The shopper pays on the retailer site. Product names and prices come from each retailer's public storefront at request time. OAuth client registrations and Outpost cart plans may be stored when a database is configured.</p>
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
                "description": "Search grocery storefronts. Kettle Range and Outpost checkout start a cart the shopper pays for on the store site.",
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

    @mcp.custom_route("/outpost-cart/{cart_id}", methods=["GET"])
    async def outpost_cart_page(request: Request) -> HTMLResponse:
        plan = await load_outpost_cart(request.path_params["cart_id"])
        if plan is None:
            return HTMLResponse("<h1>Cart not found</h1>", status_code=404)
        page = render_outpost_cart_page(
            plan,
            plan_url_for(host, request.path_params["cart_id"]),
            request.path_params["cart_id"],
        )
        return HTMLResponse(page)

    @mcp.custom_route("/outpost-cart/{cart_id}/plan.json", methods=["GET"])
    async def outpost_cart_plan(request: Request) -> JSONResponse:
        plan = await load_outpost_cart(request.path_params["cart_id"])
        if plan is None:
            return JSONResponse({"error": "Cart not found"}, status_code=404)
        response = JSONResponse(plan_json(plan))
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Cache-Control"] = "no-store"
        return response
