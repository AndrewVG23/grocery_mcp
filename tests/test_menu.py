import base64
from io import BytesIO

import pytest
from pypdf import PdfReader

from grocery_mcp.mcp_server import render_menu_pdf
from grocery_mcp.menus.pdf import paint_menu, qr_svg, render_menu_html
from grocery_mcp.menus.schema import MenuError, parse_cart, parse_menu, visible_cart_link
from grocery_mcp.menus.shopping_list import build_shopping_list
from grocery_mcp.menus.store import render_menu_file, shopping_list_for

CART = {
    "url": "https://shop.example/cart/filled",
    "retailer": "Outpost",
    "item_count": 4,
}
LONG_NAME = "Lemon herb chicken with a warm pan sauce"
LONG_DESCRIPTION = (
    "Bright and savory, this Tuesday plate is meant to be eaten warm, with the pan juices. Yes!"
)


def _meal(name, ingredients, description=None, course="Dinner"):
    meal = {"course": course, "name": name, "ingredients": ingredients}
    if description is not None:
        meal["description"] = description
    return meal


def _menu(*days, title="Weeknight table", subtitle="Three dinners, one list"):
    return {"title": title, "subtitle": subtitle, "days": list(days)}


def _day(label, *meals):
    return {"label": label, "meals": list(meals)}


def test_visible_cart_link_keeps_the_path_and_hides_the_query():
    url = "https://shop.example/checkout?ex_access_token=secret"
    assert visible_cart_link(url) == "shop.example/checkout"


def test_lengths_used_by_the_layout_are_at_the_limit():
    assert len(LONG_NAME) == 40
    assert len(LONG_DESCRIPTION) == 90


def test_shopping_list_sums_units_and_rounds_up_to_a_buyable_size():
    menu = parse_menu(
        _menu(
            _day(
                "Monday",
                _meal(
                    "Soup",
                    [
                        {"item": "Chicken breast", "qty": 0.4, "unit": "lb"},
                        {"item": "egg", "qty": 3, "unit": "each"},
                        {"item": "broth", "qty": 1, "unit": "cup"},
                    ],
                ),
            ),
            _day(
                "Tuesday",
                _meal(
                    "Soup again",
                    [
                        {"item": "Chicken breast", "qty": 0.4, "unit": "lb"},
                        {"item": "Eggs", "qty": 4, "unit": "each"},
                        {"item": "broth", "qty": 1.5, "unit": "cups"},
                        {"item": "salt", "qty": 2, "unit": "tsp"},
                    ],
                ),
            ),
            _day(
                "Wednesday",
                _meal("Seasoned", [{"item": "salt", "qty": 2, "unit": "tsp"}]),
            ),
        )
    )
    assert build_shopping_list(menu) == [
        {"item": "broth", "qty": 2.5, "unit": "cups"},
        {"item": "Chicken breast", "qty": 1, "unit": "lb"},
        {"item": "egg", "qty": 12, "unit": "eggs"},
        {"item": "salt", "qty": 2, "unit": "tbsp"},
    ]


@pytest.mark.asyncio
async def test_invalid_menu_returns_a_field_the_model_can_fix():
    with pytest.raises(MenuError) as caught:
        await shopping_list_for(
            _menu(_day("Monday", _meal("x" * 41, [])))
        )
    assert caught.value.fields[0]["field"] == "days.0.meals.0.name"
    assert "40" in caught.value.fields[0]["message"]


def _sample(days: int, long: bool = False):
    built = []
    for index in range(days):
        name = LONG_NAME if long and index == 0 else f"Dinner {index + 1}"
        description = LONG_DESCRIPTION if long and index == 0 else "A short plate."
        built.append(
            _day(
                f"Day {index + 1}",
                _meal(name, [{"item": "oats", "qty": 1, "unit": "cup"}], description),
            )
        )
    return _menu(*built)


@pytest.mark.asyncio
async def test_menu_pdf_pages_fit_and_the_cart_link_is_the_qr_target():
    one = parse_menu(_sample(1, long=True))
    three = parse_menu(_sample(3))
    week = parse_menu(_sample(7))
    cart = parse_cart(CART)
    one_html = render_menu_html(one, cart, "letter")
    three_html = render_menu_html(three, cart, "letter")
    week_html = render_menu_html(week, None, "letter")

    one_pdf, one_pages, one_clip = await paint_menu(one_html)
    _, three_pages, three_clip = await paint_menu(three_html)
    _, week_pages, week_clip = await paint_menu(week_html)

    assert one_pages == 1 and not one_clip
    assert three_pages == 1 and not three_clip
    assert week_pages == 3 and not week_clip
    assert one_pdf.startswith(b"%PDF")
    assert 'href="https://shop.example/cart/filled"' in three_html
    assert qr_svg(CART["url"]) in three_html
    assert "Open the filled cart" in three_html
    assert visible_cart_link(CART["url"]) in three_html
    assert 'class="shop"' not in week_html
    link = PdfReader(BytesIO(one_pdf)).pages[0]["/Annots"][0].get_object()
    assert link["/A"]["/URI"] == CART["url"]


@pytest.mark.asyncio
async def test_render_returns_the_pdf_and_does_not_store_it():
    rendered = await render_menu_file(_sample(3), CART)
    assert rendered.pages == 1
    assert rendered.filename == "weeknight-table.pdf"
    assert rendered.pdf.startswith(b"%PDF")

    result = await render_menu_pdf.fn(_sample(3), checkout_url=CART["url"])
    assert result.structured_content == {
        "pages": 1,
        "filename": "weeknight-table.pdf",
        "checkout_url": CART["url"],
    }
    missing = await render_menu_pdf.fn(_sample(1))
    assert missing["error"] == "Cart link missing"
    assert missing["fields"][0]["field"] == "checkout_url"
    resource = result.content[1].resource
    assert resource.mimeType == "application/pdf"
    assert base64.b64decode(resource.blob).startswith(b"%PDF")
    assert "pdf_url" not in result.structured_content
