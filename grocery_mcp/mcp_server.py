"""MCP tools for direct grocery product-link handoffs."""
from __future__ import annotations

import json
from typing import Any

from fastmcp import FastMCP
from fastmcp.tools.tool import ToolResult
from fastmcp.utilities.types import File

from grocery_mcp.auth import build_http_auth
from grocery_mcp.directory_pages import register_directory_pages
from grocery_mcp.menus.pdf import MenuLayoutError
from grocery_mcp.menus.schema import MenuError
from grocery_mcp.menus.store import layout_error, menu_error, render_menu_file, shopping_list_for
from grocery_mcp.models import (
    GroceryItem,
    HandoffRequest,
    RetailerId,
    TemplateRequest,
    browser_cart_session,
)
from grocery_mcp.providers.base import ProviderError
from grocery_mcp.services.shopping_lists import service

mcp = FastMCP(
    name="grocery",
    instructions=(
        "Search Kettle Range and Outpost. To place an order, call start_grocery_checkout "
        "and give the shopper checkout_url. Kettle Range opens a filled cart on the store "
        "site. Outpost returns one https link that opens the cart the server "
        "already filled. Do not ask "
        "for a card number. Do not say the order is placed until the shopper finishes "
        "checkout on the retailer site. "
        "To print a menu, you write the Menu JSON yourself. This server does not invent it. "
        "Call build_shopping_list, then start_grocery_checkout with those items, then "
        "render_menu_pdf with that checkout_url. The PDF file includes that live cart "
        "link. Do not expect a stored link. create_grocery_handoff returns "
        "product links and does not fill a cart. "
        "Always show unmatched items, prices, and availability. Never substitute a different "
        "product category just to produce a result."
    ),
    auth=build_http_auth(),
)


@mcp.tool()
async def find_grocery_retailers() -> dict[str, Any]:
    """List supported grocery retailers and pickup storefront locations."""
    return {"retailers": [location.model_dump(mode="json") for location in await service.retailers()]}


@mcp.tool()
async def search_grocery_products(
    retailer: str,
    query: str,
    location_id: str | None = None,
    limit: int = 5,
    brand: str | None = None,
) -> dict[str, Any]:
    """Search one retailer's public catalog and return ranked direct product links.

    Args:
        retailer: ``kettle_range`` or ``outpost``.
        query: Product name, such as ``boneless chicken thighs``.
        location_id: Store id from ``find_grocery_retailers``.
        limit: Maximum matches, 1-10.
        brand: Optional preferred brand.
    """
    try:
        retailer_id = RetailerId(retailer)
        matches = await service.search(
            retailer_id,
            GroceryItem(name=query, brand=brand),
            location_id=location_id,
            limit=min(max(limit, 1), 10),
        )
    except (ValueError, ProviderError) as exc:
        return {"error": str(exc)}
    return {
        "retailer": retailer_id,
        "query": query,
        "cart_prefilled": False,
        "browser_cart_session": browser_cart_session(retailer_id).model_dump(mode="json"),
        "matches": [match.model_dump(mode="json") for match in matches],
    }


@mcp.tool()
async def create_grocery_handoff(
    retailer: str,
    items: list[dict[str, Any]],
    location_id: str | None = None,
    postal_code: str | None = None,
) -> dict[str, Any]:
    """Match a grocery list to direct retailer product links for manual checkout.

    Args:
        retailer: ``kettle_range`` or ``outpost``.
        items: Grocery items with ``name`` and optional quantity/unit/brand/notes.
        location_id: Store id from ``find_grocery_retailers``.
        postal_code: Optional user postal code, retained for future retailer routing.
    """
    try:
        request = HandoffRequest(
            retailer=RetailerId(retailer),
            items=_grocery_items(items),
            location_id=location_id,
            postal_code=postal_code,
        )
        handoff = await service.create_handoff(request)
    except (ValueError, ProviderError) as exc:
        return {"error": str(exc)}
    return handoff.model_dump(mode="json")


@mcp.tool()
async def start_grocery_checkout(
    retailer: str,
    items: list[dict[str, Any]],
    location_id: str | None = None,
    postal_code: str | None = None,
) -> dict[str, Any]:
    """Start a cart the shopper pays for on the retailer site.

    Kettle Range returns the store checkout link. Outpost returns one https link
    that opens the cart this server already filled. This server does not take
    a card number or the Outpost password. The order is placed only after the
    shopper checks out there.

    For a printed menu, call build_shopping_list first and pass its items here.
    Then call render_menu_pdf with that checkout_url. The PDF opens the filled
    cart. This is the cart link for the menu, not create_grocery_handoff.

    Args:
        retailer: ``kettle_range`` or ``outpost``.
        items: Grocery items with ``name`` and optional quantity/unit/brand/notes.
            Items from build_shopping_list may use ``item``, ``qty``, and ``unit``.
        location_id: Kettle Range ``milwaukee`` or ``elm_grove``. Outpost
            ``capitol``, ``state``, ``bay_view``, or ``mequon``. Defaults to
            Milwaukee or Bay View.
        postal_code: Unused for pickup. Kept so a saved list can call this tool.
    """
    try:
        request = HandoffRequest(
            retailer=RetailerId(retailer),
            items=_grocery_items(items),
            location_id=location_id,
            postal_code=postal_code,
        )
        checkout = await service.start_checkout(request)
    except (ValueError, ProviderError) as exc:
        return {"error": str(exc)}
    return checkout.model_dump(mode="json")


@mcp.tool()
async def get_grocery_handoff(handoff_id: str) -> dict[str, Any]:
    """Retrieve a previously generated product-link handoff."""
    handoff = await service.get_handoff(handoff_id)
    if handoff is None:
        return {"error": "handoff not found"}
    return handoff.model_dump(mode="json")


@mcp.tool()
async def create_grocery_order_template(
    name: str,
    retailer: str,
    items: list[dict[str, Any]],
    location_id: str | None = None,
    postal_code: str | None = None,
) -> dict[str, Any]:
    """Save a reusable grocery list without searching or placing an order."""
    try:
        template = await service.create_template(
            TemplateRequest(
                name=name,
                retailer=RetailerId(retailer),
                items=[GroceryItem.model_validate(item) for item in items],
                location_id=location_id,
                postal_code=postal_code,
            )
        )
    except (ValueError, ProviderError) as exc:
        return {"error": str(exc)}
    return template.model_dump(mode="json")


@mcp.tool()
async def list_grocery_order_templates() -> dict[str, Any]:
    """List reusable grocery order templates saved on this service."""
    templates = await service.list_templates()
    return {"templates": [template.model_dump(mode="json") for template in templates]}


@mcp.tool()
async def create_handoff_from_template(template_id: str) -> dict[str, Any]:
    """Run fresh storefront searches for all items in a reusable template."""
    handoff = await service.create_handoff_from_template(template_id)
    if handoff is None:
        return {"error": "template not found"}
    return handoff.model_dump(mode="json")


def _grocery_items(items: list[dict[str, Any]]) -> list[GroceryItem]:
    parsed: list[GroceryItem] = []
    for raw in items:
        payload = dict(raw)
        if not payload.get("name") and payload.get("item"):
            payload["name"] = payload["item"]
        if payload.get("quantity") is None and payload.get("qty") is not None:
            payload["quantity"] = payload["qty"]
        parsed.append(GroceryItem.model_validate(payload))
    return parsed


@mcp.tool()
async def build_shopping_list(menu: dict[str, Any]) -> dict[str, Any]:
    """Sum a menu into a shopping list. You write the menu JSON; this server does not.

    Call this first. Pass the returned items to start_grocery_checkout, then call
    render_menu_pdf. Each item is ``{item, qty, unit}``. Matching units are combined
    and rounded up to a purchasable size. Eggs round up to the next dozen.

    Args:
        menu: Menu JSON with ``title``, optional ``subtitle``, and 1 to 7 ``days``.
            A day has ``label`` and 1 to 4 ``meals``. A meal has ``course``, ``name``
            (max 40 characters), optional ``description`` (max 90), and
            ``ingredients`` of ``{item, qty, unit}``.
    """
    try:
        return await shopping_list_for(menu)
    except MenuError as exc:
        return menu_error(exc)


@mcp.tool()
async def render_menu_pdf(
    menu: dict[str, Any],
    cart: dict[str, Any] | str | None = None,
    paper: str = "letter",
    checkout_url: str | None = None,
) -> Any:
    """Render the menu to a PDF and return the file. Call this after start_grocery_checkout.

    Pass ``checkout_url`` from that tool. The PDF's "Open the filled cart" link
    and QR code both open that same cart. A bare URL in ``cart`` is also accepted.
    The PDF is attached to this result. Nothing is uploaded or saved. Show the
    file to the shopper. One column is one day, and three days fit on a page.

    Args:
        menu: The same Menu JSON passed to build_shopping_list.
        cart: The checkout URL, or ``{url, retailer, item_count}``.
        paper: ``letter`` or ``a4``.
        checkout_url: The live filled-cart link from start_grocery_checkout.
    """
    try:
        rendered = await render_menu_file(menu, cart, paper, checkout_url)
    except MenuError as exc:
        return menu_error(exc)
    except MenuLayoutError as exc:
        return layout_error(exc)
    summary = {
        "pages": rendered.pages,
        "filename": rendered.filename,
        "checkout_url": rendered.checkout_url,
    }
    return ToolResult(
        content=[
            json.dumps(summary),
            File(
                data=rendered.pdf,
                format="pdf",
                name=rendered.filename.removesuffix(".pdf"),
            ),
        ],
        structured_content=summary,
    )


register_directory_pages(mcp)
