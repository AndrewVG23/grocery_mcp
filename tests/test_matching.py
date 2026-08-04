from grocery_mcp.models import GroceryItem
from grocery_mcp.providers.base import CatalogProduct, is_acceptable_match, rank_products


def product(name: str, *, available: bool = True) -> CatalogProduct:
    return CatalogProduct(id=name, name=name, url="https://example.test", available=available)


def test_rejects_partial_and_unrelated_substitutions():
    assert not is_acceptable_match(GroceryItem(name="cube steak"), product("Top Sirloin Steak"))
    assert not is_acceptable_match(
        GroceryItem(name="Yukon potatoes"),
        product("Community Food Donation"),
    )
    assert not is_acceptable_match(
        GroceryItem(name="queso fresco"),
        product("Jackfruit BBQ"),
    )


def test_rejects_processed_product_for_fresh_produce_query():
    assert not is_acceptable_match(
        GroceryItem(name="bell peppers"),
        product("Bell Pepper Monterey Jack Cheese"),
    )
    assert is_acceptable_match(
        GroceryItem(name="bell peppers"),
        product("Organic Red Bell Pepper"),
    )


def test_prefers_available_match_when_relevance_is_comparable():
    item = GroceryItem(name="black beans")
    ranked = rank_products(
        item,
        [
            product("Black Beans", available=False),
            product("Organic Black Beans", available=True),
        ],
        limit=2,
    )
    assert ranked[0].available is True
