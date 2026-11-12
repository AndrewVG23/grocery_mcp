from __future__ import annotations

from grocery_mcp.models import (
    GroceryItem,
    HandoffRequest,
    ProductMatch,
    RetailerId,
    RetailerLocation,
    TemplateRequest,
    browser_cart_session,
)
from grocery_mcp.open_outpost_cart import plan_endpoint
from grocery_mcp.outpost_checkout import (
    load_outpost_cart,
    load_outpost_session,
    render_outpost_cart_page,
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


def test_outpost_links_do_not_join_a_cart_opened_from_another_site():
    session = browser_cart_session(RetailerId.OUTPOST)
    assert session.product_link_keeps_store_login is False
    assert session.server_can_add_to_that_cart is False
    assert "Outpost" in session.note


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
    assert handoff.browser_cart_session is not None
    assert handoff.browser_cart_session.server_can_add_to_that_cart is False
    assert handoff.browser_cart_session.product_link_keeps_store_login is True
    assert handoff.warnings == [handoff.browser_cart_session.note]
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


async def test_reusable_template_creates_fresh_handoff():
    service = ShoppingListService({RetailerId.KETTLE_RANGE: StubProvider()})
    template = await service.create_template(
        TemplateRequest(
            name="Taco night",
            retailer=RetailerId.KETTLE_RANGE,
            location_id="test",
            items=[
                GroceryItem(name="ground beef"),
                GroceryItem(name="ground beef", quantity=2),
            ],
        )
    )

    assert template.name == "Taco night"
    assert template.items[0].quantity == 3
    assert await service.get_template(template.id) == template

    handoff = await service.create_handoff_from_template(template.id)
    assert handoff is not None
    assert handoff.results[0].match.name == "Matched ground beef"


class _CartProvider(StubProvider):
    async def start_pickup_cart(self, location_id, products):
        return {
            "checkout_url": "https://shop.kettlerangemeats.com/checkout?ex_access_token=test",
            "total_text": "$6.25",
            "lines": [
                {
                    "requested_name": products[0]["requested_name"],
                    "product_name": "Boneless chicken thighs",
                    "quantity": products[0]["quantity"],
                    "price_text": "$6.25",
                }
            ],
            "skipped": [],
        }


async def test_kettle_checkout_returns_the_store_link():
    service = ShoppingListService({RetailerId.KETTLE_RANGE: _CartProvider()})
    checkout = await service.start_checkout(
        HandoffRequest(
            retailer=RetailerId.KETTLE_RANGE,
            location_id="test",
            items=[GroceryItem(name="chicken thighs", quantity=2)],
        )
    )
    assert checkout.cart_prefilled is True
    assert checkout.requires_user_checkout is True
    assert checkout.checkout_url.endswith("ex_access_token=test")
    assert checkout.lines[0].product_name == "Boneless chicken thighs"
    assert checkout.lines[0].quantity == 2
    assert checkout.total_text == "$6.25"
    assert checkout.unmatched == []


class _OutpostProvider(StubProvider):
    retailer = RetailerId.OUTPOST

    async def locations(self):
        return [
            RetailerLocation(
                id="bay_view",
                retailer=self.retailer,
                name="Outpost Bay View",
                storefront_url="https://shop.outpost.coop/s/1000-5/",
            )
        ]

    async def search(self, item, location_id=None, limit=5):
        matches = await super().search(item, location_id=location_id, limit=limit)
        matches[0].price = 3.49
        matches[0].price_text = "$3.49"
        matches[0].product_id = "INV-1000-8"
        return matches

    async def start_filled_cart(self, location, lines):
        return {
            "grand_total": 6.98,
            "line_count": len(lines),
            "cookies": [
                {
                    "name": "token",
                    "value": "guest-session",
                    "domain": "shop.outpost.coop",
                    "path": "/",
                }
            ],
        }


async def test_outpost_checkout_fills_the_shoppers_store_tab():
    service = ShoppingListService({RetailerId.OUTPOST: _OutpostProvider()})
    checkout = await service.start_checkout(
        HandoffRequest(
            retailer=RetailerId.OUTPOST,
            location_id="bay_view",
            items=[GroceryItem(name="bananas", quantity=2)],
        )
    )
    cart_id = checkout.checkout_url.split("/outpost-cart/")[1].split("/")[0]
    plan = await load_outpost_cart(cart_id)
    assert checkout.cart_prefilled is True
    assert checkout.requires_user_checkout is True
    assert checkout.checkout_url.endswith(f"/outpost-cart/{cart_id}/shop/s/1000-5/co")
    assert "outpostcart://" not in checkout.checkout_url
    assert checkout.lines[0].product_name == "Matched bananas"
    assert checkout.total_text == "$6.98"
    assert plan["cart_api"] == "https://shop.outpost.coop/s/1000-5/api/cart"
    assert "cookies" not in plan
    assert plan["items"] == [{"item": "INV-1000-8", "quantity": 2, "substitutable": True}]
    assert "already filled" in checkout.note
    session = await load_outpost_session(cart_id)
    assert session["cookies"][0]["name"] == "token"
    page = render_outpost_cart_page(
        plan,
        f"https://example.test/outpost-cart/{cart_id}/plan.json",
        cart_id,
    )
    assert "× 2" in page
    assert "outpostcart://" not in page
    assert "expired" in page
    assert plan_endpoint(f"outpostcart://{cart_id}").endswith(f"/outpost-cart/{cart_id}/plan.json")
