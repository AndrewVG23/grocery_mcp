from __future__ import annotations

import httpx

from grocery_mcp.cache import TTLCache
from grocery_mcp.models import GroceryItem
from grocery_mcp.providers import kettle_range
from grocery_mcp.providers.kettle_range import KettleRangeProvider


async def test_kettle_range_search_cache_avoids_repeat_storefront_calls():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if request.url.path.endswith("/whoami"):
            return httpx.Response(200, json={"data": {"token": "guest-token"}})
        return httpx.Response(
            200,
            json={
                "data": {
                    "products": [
                        {
                            "id": "1",
                            "title": "Grass Fed Beef",
                            "upc": "1",
                            "priceFullDecimal": 12.5,
                            "priceFull": "$12.50",
                            "productPageUrl": "/product/1",
                            "is_instock": True,
                        }
                    ]
                }
            },
        )

    kettle_range._SEARCH_CACHE.clear()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = KettleRangeProvider(client)
        item = GroceryItem(name="grass fed beef")
        first = await provider.search(item, location_id="milwaukee", limit=5)
        second = await provider.search(item, location_id="milwaukee", limit=5)

    assert first[0].product_id == "1"
    assert second[0].product_id == "1"
    assert calls["count"] == 2


def test_ttl_cache_expires_entries():
    cache = TTLCache(ttl_seconds=1)
    cache.set("beef", ["result"])
    assert cache.get("beef") == ["result"]

    cache._entries["beef"] = (0.0, ["stale"])
    assert cache.get("beef") is None
