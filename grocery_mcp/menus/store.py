"""Validate a menu and render its PDF. The file is returned to the caller and is not stored."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from grocery_mcp.menus.pdf import MenuLayoutError, paint_menu, render_menu_html
from grocery_mcp.menus.schema import MenuError, parse_menu, parse_paper, resolve_checkout
from grocery_mcp.menus.shopping_list import build_shopping_list


@dataclass(frozen=True)
class RenderedMenu:
    pdf: bytes
    pages: int
    filename: str
    checkout_url: str


def menu_error(exc: MenuError) -> dict[str, Any]:
    missing_cart = any(field.get("field") == "checkout_url" for field in exc.fields)
    return {
        "error": "Cart link missing" if missing_cart else "Invalid menu",
        "fields": exc.fields,
    }


def layout_error(exc: MenuLayoutError) -> dict[str, Any]:
    return {
        "error": "Menu text does not fit the page",
        "fields": [{"field": field, "message": "This text is too long for the menu layout"} for field in exc.fields],
    }


def pdf_filename(title: str) -> str:
    slug = "".join(character.lower() if character.isalnum() else "-" for character in title)
    slug = "-".join(part for part in slug.split("-") if part)
    return f"{(slug or 'menu')[:48]}.pdf"


async def shopping_list_for(payload: object) -> dict[str, Any]:
    menu = parse_menu(payload)
    return {"items": build_shopping_list(menu)}


async def render_menu_file(
    payload: object,
    cart_payload: object | None = None,
    paper: str = "letter",
    checkout_url: str | None = None,
) -> RenderedMenu:
    menu = parse_menu(payload)
    cart = resolve_checkout(cart_payload, checkout_url)
    if cart is None:
        raise MenuError(
            [
                {
                    "field": "checkout_url",
                    "message": "Pass the checkout_url from start_grocery_checkout so the PDF opens the filled cart",
                }
            ]
        )
    selected = parse_paper(paper)
    html = render_menu_html(menu, cart, selected)
    pdf, pages, overflows = await paint_menu(html)
    if overflows:
        raise MenuLayoutError(overflows)
    return RenderedMenu(
        pdf=pdf,
        pages=pages,
        filename=pdf_filename(menu.title),
        checkout_url=cart.url,
    )
