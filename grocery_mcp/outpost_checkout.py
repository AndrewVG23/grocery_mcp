"""An Outpost cart the shopper fills from inside their own store tab."""

from __future__ import annotations

from html import escape
from typing import Any
from urllib.parse import quote

from grocery_mcp.database import get_state, put_state

_CARTS: dict[str, dict[str, Any]] = {}
_KIND = "outpost_cart"


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
    del plan_url
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
    unmatched = "".join(
        f"<li>{escape(str(name))}</li>" for name in plan.get("unmatched") or []
    )
    store = escape(str(plan.get("store_name") or "Outpost"))
    open_url = escape(f"outpostcart://{cart_id}", quote=True) if cart_id else ""
    opener = (
        f'<p><a class="button" href="{open_url}">Open the filled cart</a></p>'
        if open_url
        else ""
    )
    missing = f"<h2>Not added</h2><ul>{unmatched}</ul>" if unmatched else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{store} cart</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body {{ font-family: system-ui, sans-serif; max-width: 42rem; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }}
a.button, button {{ display: inline-block; margin: 0.4rem 0.6rem 0.4rem 0; padding: 0.55rem 0.9rem; background: #1c1917; color: white; text-decoration: none; border: 0; border-radius: 999px; cursor: pointer; }}
.link-row {{ display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; margin: 0.3rem 0 0.8rem; }}
.link-row a {{ word-break: break-all; }}
</style>
</head>
<body>
<h1>{store}</h1>
<p>Open the filled cart. Outpost opens with these items already in the cart. Sign in on that window to put the order on your Outpost account. This Mac remembers that sign-in. Pay on Outpost.</p>
{opener}
<h2>Items</h2>
<ul>
{''.join(rows)}
</ul>
{missing}
</body>
</html>
"""


def plan_json(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "cart_api": plan["cart_api"],
        "storefront_url": plan["storefront_url"],
        "items": plan["items"],
    }


def plan_url_for(host: str, cart_id: str) -> str:
    return f"{host}/outpost-cart/{quote(cart_id, safe='')}/plan.json"
