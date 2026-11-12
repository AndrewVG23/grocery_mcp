"""An Outpost cart the Grocery server fills, then serves through one checkout link."""

from __future__ import annotations

from html import escape
from typing import Any
from urllib.parse import quote, urlparse

from grocery_mcp.database import get_state, put_state

_CARTS: dict[str, dict[str, Any]] = {}
_SESSIONS: dict[str, dict[str, Any]] = {}
_KIND = "outpost_cart"
_SESSION_KIND = "outpost_session"


async def save_outpost_cart(cart_id: str, plan: dict[str, Any]) -> None:
    _CARTS[cart_id] = plan
    await put_state(_KIND, cart_id, plan)


async def load_outpost_cart(cart_id: str) -> dict[str, Any] | None:
    cached = _CARTS.get(cart_id)
    if cached is not None:
        return cached
    stored = await get_state(_KIND, cart_id)
    if stored is not None:
        _CARTS[cart_id] = stored
    return stored


def render_outpost_cart_page(plan: dict[str, Any], plan_url: str, cart_id: str = "") -> str:
    del plan_url, cart_id
    rows = []
    for line in plan.get("lines") or []:
        quantity = line.get("quantity") or 1
        if isinstance(quantity, float) and quantity.is_integer():
            quantity = int(quantity)
        price = escape(str(line.get("price_text") or ""))
        price_html = f" · {price}" if price else ""
        rows.append(
            "<li><strong>{name}</strong> × {qty}{price}</li>".format(
                name=escape(str(line.get("product_name") or "Item")),
                qty=escape(str(quantity)),
                price=price_html,
            )
        )
    store = escape(str(plan.get("store_name") or "Outpost"))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{store} cart</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body {{ font-family: system-ui, sans-serif; max-width: 42rem; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }}
</style>
</head>
<body>
<h1>{store}</h1>
<p>This checkout link has expired. Start a new checkout to get a filled cart.</p>
<h2>Items</h2>
<ul>
{''.join(rows)}
</ul>
</body>
</html>
"""


def shop_checkout_path(cart_id: str, storefront_url: str) -> str:
    path = urlparse(storefront_url).path or "/"
    if not path.endswith("/"):
        path += "/"
    return f"/outpost-cart/{quote(cart_id, safe='')}/shop{path}co"


async def save_outpost_session(cart_id: str, session: dict[str, Any]) -> None:
    _SESSIONS[cart_id] = session
    await put_state(_SESSION_KIND, cart_id, session)


async def load_outpost_session(cart_id: str) -> dict[str, Any] | None:
    cached = _SESSIONS.get(cart_id)
    if cached is not None:
        return cached
    stored = await get_state(_SESSION_KIND, cart_id)
    if stored is not None:
        _SESSIONS[cart_id] = stored
    return stored


def plan_json(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "cart_api": plan["cart_api"],
        "storefront_url": plan["storefront_url"],
        "items": plan["items"],
    }


def plan_url_for(host: str, cart_id: str) -> str:
    return f"{host}/outpost-cart/{quote(cart_id, safe='')}/plan.json"
