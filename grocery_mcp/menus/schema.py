"""Menu JSON shared by the shopping list and the printed menu."""

from __future__ import annotations

from urllib.parse import urlparse

from pydantic import BaseModel, Field, ValidationError, field_validator


class MenuError(Exception):
    """Invalid menu or cart JSON, with one entry per field the model can fix."""

    def __init__(self, fields: list[dict[str, str]]):
        self.fields = fields
        super().__init__("Invalid menu")


class MenuIngredient(BaseModel):
    item: str = Field(min_length=1, max_length=80)
    qty: float = Field(gt=0, le=10000)
    unit: str = Field(min_length=1, max_length=24)

    @field_validator("item", "unit")
    @classmethod
    def clean(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("This field is empty")
        return cleaned


class MenuMeal(BaseModel):
    course: str = Field(min_length=1, max_length=24)
    name: str = Field(min_length=1, max_length=40)
    description: str | None = Field(default=None, max_length=90)
    ingredients: list[MenuIngredient] = Field(default_factory=list, max_length=12)

    @field_validator("course", "name", "description")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        return cleaned or None


class MenuDay(BaseModel):
    label: str = Field(min_length=1, max_length=16)
    meals: list[MenuMeal] = Field(min_length=1, max_length=4)

    @field_validator("label")
    @classmethod
    def clean_label(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Day label is empty")
        return cleaned


class Menu(BaseModel):
    title: str = Field(min_length=1, max_length=48)
    subtitle: str | None = Field(default=None, max_length=80)
    days: list[MenuDay] = Field(min_length=1, max_length=7)

    @field_validator("title", "subtitle")
    @classmethod
    def clean_heading(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        return cleaned or None


class MenuCart(BaseModel):
    url: str = Field(min_length=1)
    retailer: str = Field(min_length=1, max_length=40)
    item_count: int | None = Field(default=None, ge=0, le=500)

    @field_validator("url")
    @classmethod
    def http_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned.startswith(("http://", "https://")):
            raise ValueError("Cart URL must start with http:// or https://")
        return cleaned

    @field_validator("retailer")
    @classmethod
    def clean_retailer(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Retailer is empty")
        return cleaned


def field_errors(exc: ValidationError) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for error in exc.errors():
        path = ".".join(str(part) for part in error["loc"])
        errors.append({"field": path or "(menu)", "message": error["msg"]})
    return errors


def parse_menu(payload: object) -> Menu:
    try:
        return Menu.model_validate(payload)
    except ValidationError as exc:
        raise MenuError(field_errors(exc)) from exc


def parse_cart(payload: object | None) -> MenuCart | None:
    if payload is None:
        return None
    try:
        return MenuCart.model_validate(payload)
    except ValidationError as exc:
        raise MenuError(field_errors(exc)) from exc


def resolve_checkout(payload: object | None, checkout_url: str | None = None) -> MenuCart | None:
    """The live cart link is checkout_url, a bare URL, or cart.url / cart.checkout_url."""
    explicit = " ".join((checkout_url or "").split())
    if isinstance(payload, str):
        body: dict[str, object] = {"url": payload.strip(), "retailer": "Cart"}
    elif isinstance(payload, dict):
        body = dict(payload)
        if not body.get("url"):
            nested = body.get("checkout_url")
            body["url"] = nested.strip() if isinstance(nested, str) else ""
        body.setdefault("retailer", "Cart")
    elif payload is None:
        body = {"url": "", "retailer": "Cart"}
    else:
        raise MenuError([{"field": "cart", "message": "Cart must be a checkout URL or an object"}])
    if explicit:
        body["url"] = explicit
    if not str(body.get("url") or "").strip():
        return None
    return parse_cart(body)


def visible_cart_link(url: str) -> str:
    """Host and path only, so a token in the query string is not printed on the page."""
    parsed = urlparse(url)
    visible = f"{parsed.netloc}{parsed.path}".rstrip("/")
    if len(visible) <= 78:
        return visible or url
    return f"{visible[:40]}…{visible[-28:]}"


def parse_paper(paper: str) -> str:
    cleaned = paper.strip().lower()
    if cleaned not in {"letter", "a4"}:
        raise MenuError(
            [{"field": "paper", "message": "Paper must be letter or a4"}]
        )
    return cleaned
