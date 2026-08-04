"""Retailer provider contracts and shared matching helpers."""
from __future__ import annotations

import re
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


_WORD_PATTERN = re.compile(r"[a-z0-9]+")
_IGNORED_WORDS = {"a", "an", "and", "for", "of", "organic", "the"}
_PRODUCE_WORDS = {
    "avocado",
    "cabbage",
    "cilantro",
    "garlic",
    "jalapeno",
    "onion",
    "pepper",
    "potato",
    "tomatillo",
    "tomato",
}
_NON_PRODUCE_PRODUCTS = {
    "cheese",
    "chips",
    "donation",
    "dressing",
    "jackfruit",
    "mix",
    "sauce",
    "seasoning",
    "soup",
}


def _singularize(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return f"{word[:-3]}y"
    if len(word) > 4 and word.endswith("oes"):
        return word[:-2]
    if len(word) > 3 and word.endswith("es") and word[-3] in {"s", "x", "z"}:
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def product_tokens(value: str) -> set[str]:
    return {
        _singularize(word)
        for word in _WORD_PATTERN.findall(value.casefold())
        if word not in _IGNORED_WORDS
    }


def score_product(item: GroceryItem, product: CatalogProduct) -> float:
    query = " ".join(part for part in (item.brand, item.name) if part)
    fuzzy_score = WRatio(query.casefold(), product.name.casefold()) / 100
    query_tokens = product_tokens(query)
    name_tokens = product_tokens(product.name)
    coverage = len(query_tokens & name_tokens) / len(query_tokens) if query_tokens else 0
    score = fuzzy_score * 0.45 + coverage * 0.55
    if item.brand and product.brand:
        brand_score = WRatio(item.brand.casefold(), product.brand.casefold()) / 100
        score = score * 0.85 + brand_score * 0.15
    return round(min(max(score, 0), 1), 3)


def is_acceptable_match(item: GroceryItem, product: CatalogProduct) -> bool:
    """Reject substitutions that do not preserve the requested product identity."""
    query_tokens = product_tokens(item.name)
    name_tokens = product_tokens(product.name)
    if not query_tokens:
        return False

    overlap = query_tokens & name_tokens
    required_coverage = 1.0 if len(query_tokens) <= 2 else 0.67
    if len(overlap) / len(query_tokens) < required_coverage:
        return False

    if query_tokens & _PRODUCE_WORDS and not query_tokens & _NON_PRODUCE_PRODUCTS:
        unexpected = (name_tokens - query_tokens) & _NON_PRODUCE_PRODUCTS
        if unexpected:
            return False
    return score_product(item, product) >= 0.65


def rank_products(
    item: GroceryItem,
    products: list[CatalogProduct],
    limit: int,
) -> list[CatalogProduct]:
    acceptable = [product for product in products if is_acceptable_match(item, product)]
    return sorted(
        acceptable,
        key=lambda product: (
            product.available is True,
            score_product(item, product),
        ),
        reverse=True,
    )[:limit]


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
