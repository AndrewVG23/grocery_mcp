"""Open a local browser with an Outpost cart already filled.

The shopper pays in that window. A persistent browser profile keeps an Outpost
sign-in on this Mac. This process does not read or store the password or card.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import httpx

PUBLIC_HOST = "https://grocery-mcp-production.up.railway.app"
_FILL = """
async (plan) => {
  const headers = {
    "Accept": "application/vnd.ecrs.webcart-2.0+json, application/json",
    "Content-Type": "application/json"
  };
  const cart = await fetch(plan.cart_api, {headers, credentials: "include"}).then((response) => response.json());
  const body = {
    transaction: cart.transaction,
    instructions: cart.instructions || "",
    items: plan.items,
    giftCardItems: [],
    inStore: cart.inStore,
    checkout: cart.checkout,
    orderTypeId: cart.orderType,
    deliveryTotal: cart.deliveryTotal,
    lastSyncTime: cart.lastSyncTime
  };
  const saved = await fetch(plan.cart_api, {
    method: "POST",
    headers,
    credentials: "include",
    body: JSON.stringify(body)
  }).then((response) => response.json());
  const lines = saved.lineItems || [];
  return {
    id: saved.id || "",
    total: saved.grandTotal,
    count: lines.length,
    message: saved.message || ""
  };
}
"""


def plan_endpoint(argument: str) -> str:
    value = argument.strip()
    if value.startswith("http://") or value.startswith("https://"):
        if value.endswith("/plan.json"):
            return value
        return value.rstrip("/") + "/plan.json"
    cart_id = value.split("://", 1)[-1].strip("/")
    return f"{PUBLIC_HOST}/outpost-cart/{cart_id}/plan.json"


def _use_local_browsers() -> None:
    cache = Path.home() / "Library/Caches/ms-playwright"
    if cache.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(cache)


def _profile_dir() -> Path:
    path = Path.home() / "Library/Application Support/grocery-mcp/outpost-browser"
    path.mkdir(parents=True, exist_ok=True)
    return path


async def open_filled_cart(plan: dict) -> None:
    _use_local_browsers()
    from playwright.async_api import async_playwright

    storefront = str(plan["storefront_url"])
    if not storefront.endswith("/"):
        storefront += "/"
    playwright = await async_playwright().start()
    context = await playwright.chromium.launch_persistent_context(
        str(_profile_dir()),
        headless=False,
        args=["--start-maximized"],
        no_viewport=True,
    )
    page = context.pages[0] if context.pages else await context.new_page()
    await page.goto(storefront, wait_until="domcontentloaded")
    await page.get_by_role("button", name="Shopping cart").first.wait_for(timeout=20000)
    signed_in = await page.get_by_role("button", name="Sign In").count() == 0
    print("outpost account" if signed_in else "outpost guest", flush=True)
    result = await page.evaluate(_FILL, plan)
    print(
        f"cart {result.get('id')} total {result.get('total')} lines {result.get('count')}",
        flush=True,
    )
    if not result.get("count"):
        print(result.get("message") or "Outpost did not add these items.", flush=True)
    await page.goto(storefront + "co", wait_until="domcontentloaded")
    continue_button = page.get_by_role("button", name="Continue to shop here")
    if await continue_button.count():
        await continue_button.first.click()
    print(f"checkout {page.url}", flush=True)
    await page.wait_for_event("close", timeout=0)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m grocery_mcp.open_outpost_cart CART")
    endpoint = plan_endpoint(sys.argv[1])
    plan = httpx.get(endpoint, timeout=30).json()
    asyncio.run(open_filled_cart(plan))


if __name__ == "__main__":
    main()
