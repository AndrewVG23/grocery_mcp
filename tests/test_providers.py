from __future__ import annotations

import json

import httpx

from grocery_mcp.models import GroceryItem
from grocery_mcp.providers.kettle_range import KettleRangeProvider
from grocery_mcp.providers.outpost import OutpostProvider


async def test_kettle_range_parses_and_ranks_products():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if request.url.path.endswith("/whoami"):
            return httpx.Response(200, json={"data": {"token": "guest-token"}})
        assert request.headers["Authorization"] == "Bearer guest-token"
        assert request.url.params["mode"] == "pickup"
        return httpx.Response(
            200,
            json={
                "data": {
                    "products": [
                        {
                            "id": "2",
                            "title": "Chicken Curry",
                            "upc": "2",
                            "priceFullDecimal": 16.95,
                            "priceFull": "$16.95",
                            "productPageUrl": "/product/2",
                            "is_instock": True,
                        },
                        {
                            "id": "1",
                            "title": "Boneless Skinless Chicken Thighs",
                            "upc": "1",
                            "brand": "Kettle Range",
                            "priceFullDecimal": 6.25,
                            "priceFull": "$6.25",
                            "productPageUrl": "/product/1",
                            "is_instock": True,
                        },
                    ]
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        results = await KettleRangeProvider(client).search(
            GroceryItem(name="boneless chicken thighs"),
            location_id="milwaukee",
        )

    assert calls["count"] == 2
    assert results[0].product_id == "1"
    assert results[0].price == 6.25
    assert results[0].product_url.endswith("/product/1")


async def test_kettle_range_starts_a_pickup_cart():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/whoami"):
            return httpx.Response(200, json={"data": {"token": "guest-token"}})
        if request.url.path.endswith("/user/set-selected-store"):
            assert request.headers["Authorization"] == "Bearer guest-token"
            assert json.loads(request.content) == {"storeId": 3733}
            return httpx.Response(200, json={"data": {"result": 1}})
        assert request.url.path.endswith("/layout/cart/add-bulk")
        assert json.loads(request.content) == {
            "products": [
                {"storeProductId": "16992082", "quantity": 2, "mode": "pickup"}
            ],
            "force": 0,
            "deliveryMode": "pickup",
            "short": 0,
        }
        return httpx.Response(
            200,
            json={
                "code": "OK",
                "data": {
                    "totalFormatted": "$19.90",
                    "addedProductsData": [
                        {
                            "storeProductId": 16992082,
                            "productName": "Grass Fed Ground Beef (80:20)",
                            "productPrice": "9.95",
                            "productQuantity": 2,
                        }
                    ],
                    "skippedProducts": [],
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        cart = await KettleRangeProvider(client).start_pickup_cart(
            "milwaukee",
            [
                {
                    "store_product_id": "16992082",
                    "quantity": 2,
                    "requested_name": "ground beef",
                }
            ],
        )

    assert cart["checkout_url"] == (
        "https://shop.kettlerangemeats.com/checkout?ex_access_token=guest-token"
    )
    assert cart["total_text"] == "$19.90"
    assert cart["lines"][0]["product_name"] == "Grass Fed Ground Beef (80:20)"
    assert cart["lines"][0]["requested_name"] == "ground beef"
    assert cart["lines"][0]["quantity"] == 2
    assert cart["lines"][0]["price_text"] == "$9.95"


async def test_outpost_parses_weighted_product_and_stock():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/api/b/")
        return httpx.Response(
            200,
            json={
                "code": 0,
                "items": [
                    {
                        "id": "INV-1000-14233",
                        "name": "CHICKEN THIGHS",
                        "brand": "MILLER POULTRY",
                        "actualPrice": 3.49,
                        "actualPriceDivider": 1,
                        "size": "PER LB",
                        "outOfStock": True,
                        "sellOutOfStock": True,
                        "image": "1000-1",
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        results = await OutpostProvider(client).search(
            GroceryItem(name="chicken thighs"),
            location_id="bay_view",
        )

    assert results[0].available is True
    assert results[0].price_text == "$3.49 (PER LB)"
    assert results[0].product_url.endswith("/i/INV-1000-14233")
