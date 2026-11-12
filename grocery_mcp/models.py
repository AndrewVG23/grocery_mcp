"""Provider-neutral grocery search and handoff models."""
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class RetailerId(StrEnum):
    KETTLE_RANGE = "kettle_range"
    OUTPOST = "outpost"


class HandoffType(StrEnum):
    PRODUCT_LINKS = "product_links"


class GroceryItem(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    quantity: float = Field(default=1, gt=0, le=100)
    unit: str | None = Field(default=None, max_length=40)
    brand: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=300)

    @field_validator("name", "unit", "brand", "notes")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        return cleaned or None


class RetailerLocation(BaseModel):
    id: str
    retailer: RetailerId
    name: str
    address: str | None = None
    storefront_url: str


class ProductMatch(BaseModel):
    retailer: RetailerId
    location_id: str
    requested_item: GroceryItem
    product_id: str | None = None
    name: str
    brand: str | None = None
    price: float | None = None
    price_text: str | None = None
    available: bool | None = None
    product_url: str
    image_url: str | None = None
    confidence: float = Field(ge=0, le=1)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ItemResult(BaseModel):
    item: GroceryItem
    match: ProductMatch | None = None
    alternatives: list[ProductMatch] = Field(default_factory=list)
    warning: str | None = None


class HandoffRequest(BaseModel):
    retailer: RetailerId
    items: list[GroceryItem] = Field(min_length=1, max_length=80)
    location_id: str | None = None
    postal_code: str | None = Field(default=None, max_length=12)


class TemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    retailer: RetailerId
    items: list[GroceryItem] = Field(min_length=1, max_length=30)
    location_id: str | None = None
    postal_code: str | None = Field(default=None, max_length=12)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return " ".join(value.split())


class GroceryOrderTemplate(BaseModel):
    id: str
    name: str
    retailer: RetailerId
    items: list[GroceryItem]
    location_id: str | None = None
    postal_code: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def handoff_request(self) -> HandoffRequest:
        return HandoffRequest(
            retailer=self.retailer,
            items=self.items,
            location_id=self.location_id,
            postal_code=self.postal_code,
        )


class BrowserCartSession(BaseModel):
    """How a product link behaves in the shopper's own browser."""

    product_link_keeps_store_login: bool
    server_can_add_to_that_cart: bool = False
    note: str


def browser_cart_session(retailer: RetailerId) -> BrowserCartSession:
    if retailer is RetailerId.KETTLE_RANGE:
        return BrowserCartSession(
            product_link_keeps_store_login=True,
            note=(
                "Open each product link in the browser where you shop Kettle Range. "
                "That link stays in your store session and shows the product page. "
                "It does not add the item. This server cannot add it either: "
                "Kettle Range does not let another website use your store session."
            ),
        )
    return BrowserCartSession(
        product_link_keeps_store_login=False,
        note=(
            "Open the Outpost storefront first, then paste each product link into that tab. "
            "A link clicked from Claude starts a new visit, because Outpost does not send "
            "its session cookie on a click from another site. Add the item from the Outpost tab. "
            "This server cannot add it to the cart you already have."
        ),
    )


class CheckoutLine(BaseModel):
    requested_name: str
    product_name: str
    quantity: float
    price_text: str | None = None


class GroceryCheckout(BaseModel):
    """A pickup cart on the retailer's site. The shopper pays there."""

    retailer: RetailerId
    location: RetailerLocation
    checkout_url: str
    lines: list[CheckoutLine]
    unmatched: list[str] = Field(default_factory=list)
    total_text: str | None = None
    cart_prefilled: bool = True
    requires_user_checkout: bool = True
    note: str


class GroceryHandoff(BaseModel):
    id: str
    retailer: RetailerId
    location: RetailerLocation
    handoff_type: HandoffType = HandoffType.PRODUCT_LINKS
    results: list[ItemResult]
    storefront_url: str
    cart_prefilled: bool = False
    requires_user_checkout: bool = True
    browser_cart_session: BrowserCartSession | None = None
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
