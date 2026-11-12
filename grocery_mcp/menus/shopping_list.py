"""Sum menu ingredients into quantities a shopper can buy."""

from __future__ import annotations

import math
from dataclasses import dataclass

from grocery_mcp.menus.schema import Menu

_MASS_GRAMS = {
    "g": 1.0,
    "gram": 1.0,
    "grams": 1.0,
    "kg": 1000.0,
    "kilogram": 1000.0,
    "kilograms": 1000.0,
    "oz": 28.349523125,
    "ounce": 28.349523125,
    "ounces": 28.349523125,
    "lb": 453.59237,
    "lbs": 453.59237,
    "pound": 453.59237,
    "pounds": 453.59237,
}
_VOLUME_ML = {
    "ml": 1.0,
    "milliliter": 1.0,
    "milliliters": 1.0,
    "l": 1000.0,
    "liter": 1000.0,
    "liters": 1000.0,
    "tsp": 4.92892159375,
    "teaspoon": 4.92892159375,
    "teaspoons": 4.92892159375,
    "tbsp": 14.78676478125,
    "tablespoon": 14.78676478125,
    "tablespoons": 14.78676478125,
    "cup": 236.5882365,
    "cups": 236.5882365,
    "fl oz": 29.5735295625,
    "floz": 29.5735295625,
    "fluid ounce": 29.5735295625,
    "fluid ounces": 29.5735295625,
}
_COUNT = {
    "each": "each",
    "ct": "each",
    "count": "each",
    "piece": "piece",
    "pieces": "piece",
    "clove": "clove",
    "cloves": "clove",
    "bunch": "bunch",
    "bunches": "bunch",
    "can": "can",
    "cans": "can",
    "package": "package",
    "packages": "package",
    "pkg": "package",
    "head": "head",
    "heads": "head",
    "bag": "bag",
    "bags": "bag",
    "jar": "jar",
    "jars": "jar",
    "stick": "stick",
    "sticks": "stick",
    "slice": "slice",
    "slices": "slice",
    "sprig": "sprig",
    "sprigs": "sprig",
}
_PLURAL = {
    "each": "each",
    "piece": "pieces",
    "clove": "cloves",
    "bunch": "bunches",
    "can": "cans",
    "package": "packages",
    "head": "heads",
    "bag": "bags",
    "jar": "jars",
    "stick": "sticks",
    "slice": "slices",
    "sprig": "sprigs",
    "egg": "eggs",
}


@dataclass
class _Line:
    item: str
    kind: str
    amount: float
    unit: str


def build_shopping_list(menu: Menu) -> list[dict[str, object]]:
    """Sum ingredients across meals and round up to a purchasable size."""
    grouped: dict[tuple[str, str], _Line] = {}
    for day in menu.days:
        for meal in day.meals:
            for ingredient in meal.ingredients:
                key_name = _item_key(ingredient.item)
                kind, amount, unit = _measure(ingredient.qty, ingredient.unit)
                key = (key_name, kind if kind != "opaque" else f"opaque:{unit}")
                current = grouped.get(key)
                if current is None:
                    grouped[key] = _Line(ingredient.item, kind, amount, unit)
                else:
                    current.amount += amount
    items = [_finish(line) for line in grouped.values()]
    items.sort(key=lambda row: str(row["item"]).casefold())
    return items


def _item_key(name: str) -> str:
    key = " ".join(name.casefold().split())
    if _is_egg(key):
        return "egg"
    return key


def _is_egg(name: str) -> bool:
    tokens = name.casefold().split()
    if tokens and tokens[0] in {"large", "xl", "extra-large"}:
        tokens = tokens[1:]
    return tokens in (["egg"], ["eggs"])


def _unit_text(unit: str) -> str:
    return " ".join(unit.strip().casefold().replace(".", "").split())


def _measure(qty: float, unit: str) -> tuple[str, float, str]:
    text = _unit_text(unit)
    if text in _MASS_GRAMS:
        return "mass", qty * _MASS_GRAMS[text], text
    if text in _VOLUME_ML:
        return "volume", qty * _VOLUME_ML[text], text
    if text in _COUNT:
        return "count", qty, _COUNT[text]
    return "opaque", qty, text or "each"


def _ceil_step(value: float, step: float) -> float:
    steps = math.ceil((value / step) - 1e-9)
    return round(steps * step, 4)


def _qty_out(value: float) -> int | float:
    nearest = round(value)
    if abs(value - nearest) < 1e-6:
        return int(nearest)
    return round(value, 2)


def _count_unit(unit: str, qty: float) -> str:
    if qty == 1:
        return unit
    return _PLURAL.get(unit, unit)


def _finish(line: _Line) -> dict[str, object]:
    if line.kind == "mass":
        pounds = line.amount / _MASS_GRAMS["lb"]
        if pounds >= 0.25:
            qty = _ceil_step(pounds, 0.25)
            return {"item": line.item, "qty": _qty_out(qty), "unit": "lb"}
        ounces = line.amount / _MASS_GRAMS["oz"]
        if ounces >= 1:
            return {"item": line.item, "qty": _qty_out(_ceil_step(ounces, 1)), "unit": "oz"}
        return {"item": line.item, "qty": _qty_out(_ceil_step(line.amount, 1)), "unit": "g"}
    if line.kind == "volume":
        cups = line.amount / _VOLUME_ML["cup"]
        if cups >= 1:
            qty = _ceil_step(cups, 0.25)
            unit = "cup" if qty == 1 else "cups"
            return {"item": line.item, "qty": _qty_out(qty), "unit": unit}
        tablespoons = line.amount / _VOLUME_ML["tbsp"]
        if tablespoons >= 1:
            return {
                "item": line.item,
                "qty": _qty_out(_ceil_step(tablespoons, 1)),
                "unit": "tbsp",
            }
        teaspoons = line.amount / _VOLUME_ML["tsp"]
        return {"item": line.item, "qty": _qty_out(_ceil_step(teaspoons, 0.25)), "unit": "tsp"}
    if line.kind == "count" and _is_egg(line.item):
        dozens = _ceil_step(line.amount / 12, 1) * 12
        qty = _qty_out(dozens)
        return {"item": line.item, "qty": qty, "unit": _count_unit("egg", float(qty))}
    if line.kind == "count":
        qty = _qty_out(_ceil_step(line.amount, 1))
        return {"item": line.item, "qty": qty, "unit": _count_unit(line.unit, float(qty))}
    qty = _qty_out(_ceil_step(line.amount, 1))
    return {"item": line.item, "qty": qty, "unit": line.unit}
