"""Read-only Kettle Range Meat Co. Local Express catalog adapter."""
from __future__ import annotations

import base64
import time
from typing import Any
from urllib.parse import urljoin

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

STOREFRONT = "https://shop.kettlerangemeats.com"
API_BASE = f"{STOREFRONT}/rest-proxy/v2"

KETTLE_LOCATIONS = {
    "milwaukee": RetailerLocation(
        id="milwaukee",
        retailer=RetailerId.KETTLE_RANGE,
        name="Kettle Range Meat Co. - Milwaukee",
        address="5501 W State St, Milwaukee, WI 53208",
        storefront_url=f"{STOREFRONT}/store/kettle-range-meat-co",
    ),
    "elm_grove": RetailerLocation(
        id="elm_grove",
        retailer=RetailerId.KETTLE_RANGE,
        name="Kettle Range Meat Co. - Elm Grove",
        address="13402 Watertown Plank Rd, Elm Grove, WI 53122",
        storefront_url=f"{STOREFRONT}/store/kettle-range-meat-co-elm-grove",
    ),
}

STORE_IDS = {"milwaukee": "3733", "elm_grove": "3914"}
_TOKEN_TTL_SECONDS = 1800
_SEARCH_CACHE = TTLCache(cache_ttl_seconds())


def _encode_search(value: str) -> str:
    return base64.urlsafe_b64encode(value.strip().encode()).decode().rstrip("=")


def _catalog_product(raw: dict[str, Any]) -> CatalogProduct:
    relative_url = raw.get("productPageUrl") or f"/product/{raw.get('upc', raw.get('id', ''))}"
    return CatalogProduct(
        id=str(raw.get("id") or raw.get("upc") or "") or None,
        name=str(raw.get("title") or raw.get("name") or "Unknown product"),
        brand=raw.get("brand"),
        price=float(raw["priceFullDecimal"]) if raw.get("priceFullDecimal") is not None else None,
        price_text=raw.get("priceFull") or raw.get("price"),
        available=bool(raw.get("is_instock", True)),
        url=urljoin(STOREFRONT, relative_url),
        image_url=raw.get("image") or raw.get("thumbImage"),
        raw=raw,
    )


class KettleRangeProvider(RetailerProvider):
    retailer = RetailerId.KETTLE_RANGE

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._token: str | None = None
        self._token_expires_at = 0.0

    async def locations(self) -> list[RetailerLocation]:
        return list(KETTLE_LOCATIONS.values())

    def _client_for(self) -> httpx.AsyncClient:
        return self._client or storefront_client()

    async def _guest_token(self, client: httpx.AsyncClient) -> str:
        now = time.monotonic()
        if self._token and now < self._token_expires_at:
            return self._token

        whoami = await client.get(f"{API_BASE}/whoami")
        whoami.raise_for_status()
        token = (whoami.json().get("data") or {}).get("token")
        if not token:
            raise ProviderError("Kettle Range did not issue a guest catalog token.")

        self._token = token
        self._token_expires_at = now + _TOKEN_TTL_SECONDS
        return token

    async def _search_raw(self, query: str, location_id: str, limit: int) -> list[dict[str, Any]]:
        store_id = STORE_IDS.get(location_id)
        if store_id is None:
            raise ProviderError(f"Unknown Kettle Range location: {location_id}")

        normalized_query = query.strip().casefold()
        cache_key = f"{location_id}:{normalized_query}:{limit}"
        cached = _SEARCH_CACHE.get(cache_key)
        if cached is not None:
            return cached

        client = self._client_for()
        try:
            token = await self._guest_token(client)
            response = await client.post(
                f"{API_BASE}/layout/stores/{store_id}/products/search",
                params={"mode": "pickup", "limit": min(max(limit, 1), 20)},
                json={"eSearch": _encode_search(query)},
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            payload = response.json().get("data") or {}
            products = payload.get("products") or payload.get("result") or []
            if not isinstance(products, list):
                raise ProviderError("Kettle Range returned an unexpected catalog response.")
            _SEARCH_CACHE.set(cache_key, products)
            return products
        except httpx.HTTPError as exc:
            raise ProviderError(f"Kettle Range catalog request failed: {exc}") from exc

    async def search(
        self,
        item: GroceryItem,
        location_id: str | None = None,
        limit: int = 5,
    ) -> list[ProductMatch]:
        selected = location_id or "milwaukee"
        if selected not in KETTLE_LOCATIONS:
            raise ProviderError(f"Unknown Kettle Range location: {selected}")

        fetch_limit = min(max(limit * 3, 10), 20)
        products = [
            _catalog_product(raw)
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
