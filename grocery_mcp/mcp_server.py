"""MCP tools for direct grocery product-link handoffs."""
from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from grocery_mcp.auth import build_http_auth
from grocery_mcp.directory_pages import register_directory_pages
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
            items=[GroceryItem.model_validate(item) for item in items],
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

    Args:
        retailer: ``kettle_range`` or ``outpost``.
        items: Grocery items with ``name`` and optional quantity/unit/brand/notes.
        location_id: Kettle Range ``milwaukee`` or ``elm_grove``. Outpost
            ``capitol``, ``state``, ``bay_view``, or ``mequon``. Defaults to
            Milwaukee or Bay View.
        postal_code: Unused for pickup. Kept so a saved list can call this tool.
    """
    try:
        request = HandoffRequest(
            retailer=RetailerId(retailer),
            items=[GroceryItem.model_validate(item) for item in items],
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


register_directory_pages(mcp)
