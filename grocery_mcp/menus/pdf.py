"""Render a menu to HTML and a print-ready PDF. Fonts are read from disk."""

from __future__ import annotations

import base64
import os
import re
from html import escape, unescape
from io import BytesIO
from pathlib import Path

import segno
from pypdf import PdfReader, PdfWriter
from pypdf.annotations import Link

from grocery_mcp.menus.schema import Menu, MenuCart, visible_cart_link

_ROOT = Path(__file__).resolve().parent
_PAGE = {
    "letter": ("size: 11in 8.5in;", "width: 11in; height: 8.5in;"),
    "a4": ("size: 297mm 210mm;", "width: 297mm; height: 210mm;"),
}


class MenuLayoutError(Exception):
    def __init__(self, fields: list[str]):
        self.fields = fields
        super().__init__("Menu text does not fit the page")


def render_menu_html(menu: Menu, cart: MenuCart | None, paper: str) -> str:
    page_size, sheet_size = _PAGE[paper]
    template = (_ROOT / "template.html").read_text(encoding="utf-8")
    days = list(menu.days)
    sheets = []
    for index in range(0, len(days), 3):
        chunk = days[index : index + 3]
        columns = [_day_html(day, index + offset) for offset, day in enumerate(chunk)]
        columns.extend('<section class="day day-empty"></section>' for _ in range(3 - len(chunk)))
        sheets.append(
            "<section class=\"sheet\">"
            f"<header><h1 data-fit=\"title\">{escape(menu.title)}</h1>"
            f"{_subtitle(menu.subtitle)}"
            "</header>"
            f"<div class=\"columns\">{''.join(columns)}</div>"
            f"{_footer(cart)}"
            "</section>"
        )
    return (
        template.replace("__TITLE__", escape(menu.title))
        .replace("__FONT_CSS__", _font_css())
        .replace("__PAGE_SIZE__", page_size)
        .replace("__SHEET_SIZE__", sheet_size)
        .replace("__SHEETS__", "".join(sheets))
    )


def qr_svg(url: str) -> str:
    return segno.make(url, error="m").svg_inline(svgclass=None, omitsize=True)


async def paint_menu(html: str) -> tuple[bytes, int, list[str]]:
    """Print the HTML and report any text that overflows its box."""
    _prefer_local_browsers()
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        page = await browser.new_page()
        await page.set_content(html, wait_until="load")
        overflows = await page.evaluate(
            """() => {
              const clipped = [];
              for (const node of document.querySelectorAll("[data-fit], .day, .sheet")) {
                if (node.scrollHeight > node.clientHeight + 4 || node.scrollWidth > node.clientWidth + 4) {
                  clipped.push(node.getAttribute("data-fit") || node.className);
                }
              }
              return clipped;
            }"""
        )
        pdf = await page.pdf(print_background=True, prefer_css_page_size=True)
        await browser.close()
    href = _cart_href(html)
    if href:
        pdf = _stamp_cart_link(pdf, href)
    pages = len(PdfReader(BytesIO(pdf)).pages)
    return pdf, pages, list(overflows)


def _subtitle(subtitle: str | None) -> str:
    if not subtitle:
        return ""
    return f'<p class="subtitle" data-fit="subtitle">{escape(subtitle)}</p>'


def _day_html(day, index: int) -> str:
    meals = []
    for meal_index, meal in enumerate(day.meals):
        prefix = f"days.{index}.meals.{meal_index}"
        description = ""
        if meal.description:
            description = (
                f'<p class="desc" data-fit="{prefix}.description">{escape(meal.description)}</p>'
            )
        meals.append(
            "<article class=\"meal\">"
            f'<p class="course" data-fit="{prefix}.course">{escape(meal.course)}</p>'
            f'<h3 class="name" data-fit="{prefix}.name">{escape(meal.name)}</h3>'
            f"{description}</article>"
        )
    return (
        f'<section class="day" data-fit="days.{index}">'
        f'<h2 data-fit="days.{index}.label">{escape(day.label)}</h2>'
        f"{''.join(meals)}</section>"
    )


def _footer(cart: MenuCart | None) -> str:
    if cart is None:
        return ""
    href = escape(cart.url, quote=True)
    meta = []
    if cart.item_count:
        label = "item" if cart.item_count == 1 else "items"
        meta.append(f"{cart.item_count} {label}")
    if cart.retailer and cart.retailer != "Cart":
        meta.append(cart.retailer)
    aside = f'<p class="meta">{escape(" · ".join(meta))}</p>' if meta else ""
    return (
        '<footer class="shop">'
        f'<a class="cart-url" href="{href}">'
        '<span class="open">Open the filled cart</span>'
        f'<span class="address">{escape(visible_cart_link(cart.url))}</span>'
        "</a>"
        f"{aside}"
        f'<span class="qr">{qr_svg(cart.url)}</span>'
        "</footer>"
    )


def _cart_href(html: str) -> str | None:
    match = re.search(r'<a class="cart-url" href="([^"]*)"', html)
    if match is None:
        return None
    return unescape(match.group(1))


def _stamp_cart_link(pdf: bytes, url: str) -> bytes:
    """Cover the printed address with a URI annotation. The hit area is the link."""
    reader = PdfReader(BytesIO(pdf))
    writer = PdfWriter()
    writer.append(reader)
    for index, page in enumerate(writer.pages):
        width = float(page.mediabox.width)
        left = 0.48 * 72
        bottom = 0.20 * 72
        right = width - 1.05 * 72
        top = bottom + 0.46 * 72
        writer.add_annotation(
            page_number=index,
            annotation=Link(rect=(left, bottom, right, top), url=url, border=(0, 0, 0)),
        )
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _font_css() -> str:
    faces = (
        ("Fraunces", 500, "fraunces-500.woff2"),
        ("Fraunces", 700, "fraunces-700.woff2"),
        ('"DM Sans"', 400, "dm-sans-400.woff2"),
        ('"DM Sans"', 600, "dm-sans-600.woff2"),
    )
    rules = []
    for family, weight, name in faces:
        payload = base64.b64encode((_ROOT / "fonts" / name).read_bytes()).decode("ascii")
        rules.append(
            "@font-face {"
            f"font-family: {family};"
            f"src: url(data:font/woff2;base64,{payload}) format('woff2');"
            f"font-weight: {weight}; font-style: normal; font-display: block;"
            "}"
        )
    return "\n".join(rules)


def _browser_cache_ready(path: Path) -> bool:
    if not path.is_dir():
        return False
    return any(path.glob("chromium-*")) or any(path.glob("chromium_headless_shell-*"))


def _prefer_local_browsers() -> None:
    configured = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if configured and _browser_cache_ready(Path(configured)):
        return
    local = Path.home() / "Library/Caches/ms-playwright"
    if _browser_cache_ready(local):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(local)
