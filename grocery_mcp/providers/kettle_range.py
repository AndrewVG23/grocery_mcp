"""Read-only Kettle Range Meat Co. Local Express catalog adapter."""
from __future__ import annotations

import base64
from typing import Any
from urllib.parse import urljoin

import httpx

from grocery_mcp.config import request_timeout
from grocery_mcp.models import GroceryItem, ProductMatch, RetailerId, RetailerLocation
from grocery_mcp.providers.base import (
    CatalogProduct,
    ProviderError,
    RetailerProvider,
    score_product,
)

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
        self._external_client = client

    async def locations(self) -> list[RetailerLocation]:
        return list(KETTLE_LOCATIONS.values())

    async def _search_raw(self, query: str, location_id: str, limit: int) -> list[dict[str, Any]]:
        store_id = STORE_IDS.get(location_id)
        if store_id is None:
            raise ProviderError(f"Unknown Kettle Range location: {location_id}")

        owned_client = self._external_client is None
        client = self._external_client or httpx.AsyncClient(
            timeout=request_timeout(),
            follow_redirects=True,
            headers={"User-Agent": "grocery-mcp/0.1 (+catalog-link-service)"},
        )
        try:
            whoami = await client.get(f"{API_BASE}/whoami")
            whoami.raise_for_status()
            token = (whoami.json().get("data") or {}).get("token")
            if not token:
                raise ProviderError("Kettle Range did not issue a guest catalog token.")

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
            return products
        except httpx.HTTPError as exc:
            raise ProviderError(f"Kettle Range catalog request failed: {exc}") from exc
        finally:
            if owned_client:
                await client.aclose()

    async def search(
        self,
        item: GroceryItem,
        location_id: str | None = None,
        limit: int = 5,
    ) -> list[ProductMatch]:
        selected = location_id or "milwaukee"
        if selected not in KETTLE_LOCATIONS:
            raise ProviderError(f"Unknown Kettle Range location: {selected}")

        products = [_catalog_product(raw) for raw in await self._search_raw(item.name, selected, limit)]
        ranked = sorted(products, key=lambda product: score_product(item, product), reverse=True)
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
            for product in ranked[:limit]
        ]
