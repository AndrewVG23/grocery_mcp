"""Read-only Outpost Natural Foods ECRS WebCart catalog adapter."""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from grocery_mcp.cache import TTLCache
from grocery_mcp.config import cache_ttl_seconds
from grocery_mcp.models import GroceryItem, ProductMatch, RetailerId, RetailerLocation
from grocery_mcp.providers.base import (
    CatalogProduct,
    ProviderError,
    RetailerProvider,
    rank_products,
    score_product,
)
from grocery_mcp.providers.http_client import storefront_client

OUTPOST_LOCATIONS = {
    "capitol": RetailerLocation(
        id="capitol",
        retailer=RetailerId.OUTPOST,
        name="Outpost Natural Foods - Capitol Drive",
        address="100 E Capitol Dr, Milwaukee, WI 53212",
        storefront_url="https://shop.outpost.coop/s/1000-3/",
    ),
    "state": RetailerLocation(
        id="state",
        retailer=RetailerId.OUTPOST,
        name="Outpost Natural Foods - State Street",
        address="7000 W State St, Wauwatosa, WI 53213",
        storefront_url="https://shop.outpost.coop/s/1000-4/",
    ),
    "bay_view": RetailerLocation(
        id="bay_view",
        retailer=RetailerId.OUTPOST,
        name="Outpost Natural Foods - Bay View",
        address="2826 S Kinnickinnic Ave, Milwaukee, WI 53207",
        storefront_url="https://shop.outpost.coop/s/1000-5/",
    ),
    "mequon": RetailerLocation(
        id="mequon",
        retailer=RetailerId.OUTPOST,
        name="Outpost Natural Foods - Mequon",
        address="7590 W Mequon Rd, Mequon, WI 53092",
        storefront_url="https://shop.outpost.coop/s/1000-10/",
    ),
}


_SEARCH_CACHE = TTLCache(cache_ttl_seconds())


def _catalog_product(raw: dict[str, Any], location: RetailerLocation) -> CatalogProduct:
    product_id = str(raw.get("id") or "")
    # WebCart's stable detail route is /i/{inventory id}.
    product_url = f"{location.storefront_url.rstrip('/')}/i/{quote(product_id, safe='-')}"
    price = raw.get("actualPrice")
    divider = raw.get("actualPriceDivider") or 1
    normalized_price = float(price) / float(divider) if price is not None else None
    size = raw.get("size")
    price_text = f"${normalized_price:.2f}" if normalized_price is not None else None
    if price_text and size:
        price_text = f"{price_text} ({size})"
    return CatalogProduct(
        id=product_id or None,
        name=str(raw.get("name") or "Unknown product"),
        brand=raw.get("brand"),
        price=normalized_price,
        price_text=price_text,
        available=(not bool(raw.get("outOfStock", False))) or bool(raw.get("sellOutOfStock", False)),
        url=product_url,
        image_url=(
            f"{location.storefront_url.rstrip('/')}/api/img/{raw['image']}"
            if raw.get("image")
            else None
        ),
        raw=raw,
    )


class OutpostProvider(RetailerProvider):
    retailer = RetailerId.OUTPOST

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def locations(self) -> list[RetailerLocation]:
        return list(OUTPOST_LOCATIONS.values())

    def _client_for(self) -> httpx.AsyncClient:
        return self._client or storefront_client()

    async def _search_raw(self, query: str, location_id: str, limit: int) -> list[dict[str, Any]]:
        location = OUTPOST_LOCATIONS.get(location_id)
        if location is None:
            raise ProviderError(f"Unknown Outpost location: {location_id}")

        normalized_query = query.strip().casefold()
        cache_key = f"{location_id}:{normalized_query}:{limit}"
        cached = _SEARCH_CACHE.get(cache_key)
        if cached is not None:
            return cached

        client = self._client_for()
        try:
            response = await client.post(
                f"{location.storefront_url}api/b/",
                json={"q": query, "ps": min(max(limit, 1), 50), "pn": 1},
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") not in (0, None):
                raise ProviderError(
                    f"Outpost catalog error: {payload.get('message', 'unknown error')}"
                )
            products = payload.get("items") or []
            if not isinstance(products, list):
                raise ProviderError("Outpost returned an unexpected catalog response.")
            _SEARCH_CACHE.set(cache_key, products)
            return products
        except httpx.HTTPError as exc:
            raise ProviderError(f"Outpost catalog request failed: {exc}") from exc

    async def search(
        self,
        item: GroceryItem,
        location_id: str | None = None,
        limit: int = 5,
    ) -> list[ProductMatch]:
        selected = location_id or "bay_view"
        location = OUTPOST_LOCATIONS.get(selected)
        if location is None:
            raise ProviderError(f"Unknown Outpost location: {selected}")

        fetch_limit = min(max(limit * 3, 10), 20)
        products = [
            _catalog_product(raw, location)
            for raw in await self._search_raw(item.name, selected, fetch_limit)
        ]
        ranked = rank_products(item, products, limit)
        return [
            ProductMatch(
                retailer=self.retailer,
                location_id=selected,
                requested_item=item,
                product_id=product.id,
                name=product.name,
                brand=product.brand,
                price=product.price,
                price_text=product.price_text,
                available=product.available,
                product_url=product.url,
                image_url=product.image_url,
                confidence=score_product(item, product),
            )
            for product in ranked
        ]
