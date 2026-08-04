"""Retailer provider contracts and shared matching helpers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from rapidfuzz.fuzz import WRatio

from grocery_mcp.models import GroceryItem, ProductMatch, RetailerId, RetailerLocation


class ProviderError(RuntimeError):
    """A retailer storefront could not fulfill a read-only request."""


@dataclass(slots=True)
class CatalogProduct:
    id: str | None
    name: str
    url: str
    brand: str | None = None
    price: float | None = None
    price_text: str | None = None
    available: bool | None = None
    image_url: str | None = None
    raw: dict[str, Any] | None = None


def score_product(item: GroceryItem, product: CatalogProduct) -> float:
    query = " ".join(part for part in (item.brand, item.name) if part)
    score = WRatio(query.casefold(), product.name.casefold()) / 100
    if item.brand and product.brand:
        brand_score = WRatio(item.brand.casefold(), product.brand.casefold()) / 100
        score = score * 0.8 + brand_score * 0.2
    return round(min(max(score, 0), 1), 3)


class RetailerProvider(ABC):
    retailer: RetailerId

    @abstractmethod
    async def locations(self) -> list[RetailerLocation]:
        """Return configured retailer locations."""

    @abstractmethod
    async def search(
        self,
        item: GroceryItem,
        location_id: str | None = None,
        limit: int = 5,
    ) -> list[ProductMatch]:
        """Return ranked public product links for one requested item."""
