from __future__ import annotations

from grocery_mcp.models import (
    GroceryItem,
    HandoffRequest,
    ProductMatch,
    RetailerId,
    RetailerLocation,
)
from grocery_mcp.providers.base import ProviderError, RetailerProvider
from grocery_mcp.services.shopping_lists import ShoppingListService, normalize_items


class StubProvider(RetailerProvider):
    retailer = RetailerId.KETTLE_RANGE

    async def locations(self):
        return [
            RetailerLocation(
                id="test",
                retailer=self.retailer,
                name="Test Store",
                storefront_url="https://example.test/store",
            )
        ]

    async def search(self, item, location_id=None, limit=5):
        return [
            ProductMatch(
                retailer=self.retailer,
                location_id=location_id or "test",
                requested_item=item,
                product_id="1",
                name=f"Matched {item.name}",
                product_url="https://example.test/product/1",
                confidence=0.95,
                available=True,
            )
        ]


def test_normalize_items_merges_exact_duplicates():
    result = normalize_items(
        [
            GroceryItem(name="Chicken Thighs", quantity=1, unit="lb"),
            GroceryItem(name=" chicken   thighs ", quantity=2, unit="LB"),
        ]
    )
    assert len(result) == 1
    assert result[0].quantity == 3


async def test_create_handoff_is_explicitly_not_a_cart():
    service = ShoppingListService({RetailerId.KETTLE_RANGE: StubProvider()})
    handoff = await service.create_handoff(
        HandoffRequest(
            retailer=RetailerId.KETTLE_RANGE,
            location_id="test",
            items=[GroceryItem(name="chicken thighs")],
        )
    )
    assert handoff.cart_prefilled is False
    assert handoff.requires_user_checkout is True
    assert handoff.results[0].match.name == "Matched chicken thighs"
    assert await service.get_handoff(handoff.id) == handoff


async def test_unknown_location_is_rejected():
    service = ShoppingListService({RetailerId.KETTLE_RANGE: StubProvider()})
    try:
        await service.create_handoff(
            HandoffRequest(
                retailer=RetailerId.KETTLE_RANGE,
                location_id="missing",
                items=[GroceryItem(name="chicken")],
            )
        )
    except ProviderError as exc:
        assert "Unknown" in str(exc)
    else:
        raise AssertionError("Expected unknown location failure")
