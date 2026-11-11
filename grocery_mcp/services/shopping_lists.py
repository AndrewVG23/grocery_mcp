"""Shopping-list normalization and retailer handoff orchestration."""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from uuid import uuid4

from grocery_mcp.database import (
    list_templates as load_templates,
)
from grocery_mcp.database import (
    load_handoff,
    load_template,
    save_handoff,
    save_template,
)
from grocery_mcp.models import (
    CheckoutLine,
    GroceryCheckout,
    GroceryHandoff,
    GroceryItem,
    GroceryOrderTemplate,
    HandoffRequest,
    ItemResult,
    RetailerId,
    RetailerLocation,
    TemplateRequest,
    browser_cart_session,
)
from grocery_mcp.directory_pages import public_host
from grocery_mcp.outpost_checkout import save_outpost_cart
from grocery_mcp.providers import KettleRangeProvider, OutpostProvider
from grocery_mcp.providers.base import ProviderError, RetailerProvider


def normalize_items(items: list[GroceryItem]) -> list[GroceryItem]:
    """Merge exact duplicate requests while preserving input order."""
    merged: OrderedDict[tuple[str, str | None, str | None, str | None], GroceryItem] = (
        OrderedDict()
    )
    for item in items:
        key = (
            item.name.casefold(),
            item.unit.casefold() if item.unit else None,
            item.brand.casefold() if item.brand else None,
            item.notes.casefold() if item.notes else None,
        )
        if key in merged:
            existing = merged[key]
            merged[key] = existing.model_copy(
                update={"quantity": round(existing.quantity + item.quantity, 3)}
            )
        else:
            merged[key] = item
    return list(merged.values())


class ShoppingListService:
    def __init__(
        self,
        providers: dict[RetailerId, RetailerProvider] | None = None,
    ) -> None:
        self.providers = providers or {
            RetailerId.KETTLE_RANGE: KettleRangeProvider(),
            RetailerId.OUTPOST: OutpostProvider(),
        }
        self._handoffs: dict[str, GroceryHandoff] = {}
        self._templates: dict[str, GroceryOrderTemplate] = {}

    async def retailers(self) -> list[RetailerLocation]:
        locations: list[RetailerLocation] = []
        for provider in self.providers.values():
            locations.extend(await provider.locations())
        return locations

    async def search(
        self,
        retailer: RetailerId,
        item: GroceryItem,
        location_id: str | None = None,
        limit: int = 5,
    ):
        provider = self.providers.get(retailer)
        if provider is None:
            raise ProviderError(f"Unsupported retailer: {retailer}")
        return await provider.search(item, location_id=location_id, limit=limit)

    async def create_handoff(self, request: HandoffRequest) -> GroceryHandoff:
        provider = self.providers.get(request.retailer)
        if provider is None:
            raise ProviderError(f"Unsupported retailer: {request.retailer}")

        locations = await provider.locations()
        if not locations:
            raise ProviderError(f"No locations configured for {request.retailer}")
        location = next(
            (candidate for candidate in locations if candidate.id == request.location_id),
            locations[0],
        )
        if request.location_id and location.id != request.location_id:
            raise ProviderError(
                f"Unknown {request.retailer.value} location: {request.location_id}"
            )

        session = browser_cart_session(request.retailer)
        warnings = [session.note]
        normalized = normalize_items(request.items)

        async def resolve_item(item: GroceryItem) -> ItemResult:
            try:
                matches = await provider.search(item, location_id=location.id, limit=5)
            except ProviderError as exc:
                return ItemResult(item=item, warning=str(exc))
            if not matches:
                return ItemResult(item=item, warning="No matching products were found.")

            best, *alternatives = matches
            warning = None
            if best.confidence < 0.6:
                warning = "The best match has low confidence; review alternatives."
            if best.available is False:
                warning = "The best match is currently marked out of stock."
            return ItemResult(
                item=item,
                match=best,
                alternatives=alternatives[:3],
                warning=warning,
            )

        results = list(await asyncio.gather(*(resolve_item(item) for item in normalized)))

        handoff = GroceryHandoff(
            id=str(uuid4()),
            retailer=request.retailer,
            location=location,
            results=results,
            storefront_url=location.storefront_url,
            browser_cart_session=session,
            warnings=warnings,
        )
        self._handoffs[handoff.id] = handoff
        await save_handoff(handoff.id, handoff.model_dump(mode="json"))
        return handoff

    async def start_checkout(self, request: HandoffRequest) -> GroceryCheckout:
        """Start a cart the shopper pays for on the retailer site."""
        if request.retailer not in {RetailerId.KETTLE_RANGE, RetailerId.OUTPOST}:
            raise ProviderError(f"Unsupported retailer: {request.retailer}")
        provider = self.providers.get(request.retailer)
        if provider is None:
            raise ProviderError(f"Unsupported retailer: {request.retailer}")

        locations = await provider.locations()
        if not locations:
            raise ProviderError(f"No locations configured for {request.retailer}")
        location = next(
            (candidate for candidate in locations if candidate.id == request.location_id),
            locations[0],
        )
        if request.location_id and location.id != request.location_id:
            raise ProviderError(
                f"Unknown {request.retailer.value} location: {request.location_id}"
            )

        normalized = normalize_items(request.items)

        async def resolve_item(item: GroceryItem) -> ItemResult:
            try:
                matches = await provider.search(item, location_id=location.id, limit=5)
            except ProviderError as exc:
                return ItemResult(item=item, warning=str(exc))
            if not matches:
                return ItemResult(item=item, warning="No matching products were found.")
            best = next((match for match in matches if match.available is not False), None)
            if best is None:
                return ItemResult(
                    item=item,
                    match=matches[0],
                    warning="The best match is currently marked out of stock.",
                )
            return ItemResult(item=item, match=best)

        results = list(await asyncio.gather(*(resolve_item(item) for item in normalized)))
        cart_lines = []
        unmatched: list[str] = []
        for result in results:
            match = result.match
            if match is None or not match.product_id or match.available is False:
                unmatched.append(result.item.name)
                continue
            cart_lines.append(
                {
                    "store_product_id": match.product_id,
                    "quantity": result.item.quantity,
                    "requested_name": result.item.name,
                    "product_name": match.name,
                    "price": match.price,
                    "price_text": match.price_text,
                }
            )
        if not cart_lines:
            raise ProviderError("Nothing in stock matched this list.")

        if request.retailer is RetailerId.KETTLE_RANGE:
            start_cart = getattr(provider, "start_pickup_cart", None)
            if start_cart is None:
                raise ProviderError(f"Unsupported retailer: {request.retailer}")
            cart = await start_cart(location.id, cart_lines)
            unmatched.extend(cart["skipped"])
            return GroceryCheckout(
                retailer=request.retailer,
                location=location,
                checkout_url=cart["checkout_url"],
                lines=[CheckoutLine.model_validate(line) for line in cart["lines"]],
                unmatched=unmatched,
                total_text=cart["total_text"],
                note=(
                    "Pickup at this Kettle Range store. Open checkout_url and pay on "
                    "Kettle Range. This service does not take a card number. "
                    "The link is the guest session for this cart."
                ),
            )

        return await self._outpost_checkout(request, location, cart_lines, unmatched)

    async def _outpost_checkout(
        self,
        request: HandoffRequest,
        location: RetailerLocation,
        cart_lines: list[dict],
        unmatched: list[str],
    ) -> GroceryCheckout:
        """Save the items for a local browser window with the cart filled."""
        storefront = location.storefront_url
        if not storefront.endswith("/"):
            storefront += "/"
        lines = [
            CheckoutLine(
                requested_name=line["requested_name"],
                product_name=line["product_name"],
                quantity=line["quantity"],
                price_text=line["price_text"],
            )
            for line in cart_lines
        ]
        prices = [line["price"] for line in cart_lines]
        total_text = None
        if all(price is not None for price in prices):
            total = sum(price * line["quantity"] for price, line in zip(prices, cart_lines, strict=True))
            total_text = f"${total:.2f}"
        cart_id = str(uuid4())
        await save_outpost_cart(
            cart_id,
            {
                "store_name": location.name,
                "storefront_url": storefront,
                "cart_api": f"{storefront.rstrip('/')}/api/cart",
                "lines": [line.model_dump(mode="json") for line in lines],
                "items": [
                    {
                        "item": line["store_product_id"],
                        "quantity": int(line["quantity"])
                        if float(line["quantity"]).is_integer()
                        else line["quantity"],
                        "substitutable": True,
                    }
                    for line in cart_lines
                ],
                "unmatched": unmatched,
            },
        )
        return GroceryCheckout(
            retailer=request.retailer,
            location=location,
            checkout_url=f"{public_host()}/outpost-cart/{cart_id}",
            lines=lines,
            unmatched=unmatched,
            total_text=total_text,
            cart_prefilled=False,
            note=(
                "Open checkout_url and choose Open the filled cart. Outpost opens "
                "with these items already in the cart. Sign in on that window to put "
                "the order on the shopper's Outpost account. This Mac remembers that "
                "sign-in for the next cart. Pay on Outpost. This service does not "
                "take a card number or the Outpost password."
            ),
        )

    async def get_handoff(self, handoff_id: str) -> GroceryHandoff | None:
        handoff = self._handoffs.get(handoff_id)
        if handoff is not None:
            return handoff
        payload = await load_handoff(handoff_id)
        if payload is None:
            return None
        handoff = GroceryHandoff.model_validate(payload)
        self._handoffs[handoff_id] = handoff
        return handoff

    async def create_template(self, request: TemplateRequest) -> GroceryOrderTemplate:
        provider = self.providers.get(request.retailer)
        if provider is None:
            raise ProviderError(f"Unsupported retailer: {request.retailer}")
        locations = await provider.locations()
        if request.location_id and not any(
            location.id == request.location_id for location in locations
        ):
            raise ProviderError(
                f"Unknown {request.retailer.value} location: {request.location_id}"
            )

        template = GroceryOrderTemplate(
            id=str(uuid4()),
            name=request.name,
            retailer=request.retailer,
            items=normalize_items(request.items),
            location_id=request.location_id,
            postal_code=request.postal_code,
        )
        self._templates[template.id] = template
        await save_template(template.id, template.model_dump(mode="json"))
        return template

    async def get_template(self, template_id: str) -> GroceryOrderTemplate | None:
        template = self._templates.get(template_id)
        if template is not None:
            return template
        payload = await load_template(template_id)
        if payload is None:
            return None
        template = GroceryOrderTemplate.model_validate(payload)
        self._templates[template_id] = template
        return template

    async def list_templates(self) -> list[GroceryOrderTemplate]:
        persisted = [
            GroceryOrderTemplate.model_validate(payload)
            for payload in await load_templates()
        ]
        combined = {template.id: template for template in persisted}
        combined.update(self._templates)
        return sorted(combined.values(), key=lambda template: template.created_at, reverse=True)

    async def create_handoff_from_template(
        self,
        template_id: str,
    ) -> GroceryHandoff | None:
        template = await self.get_template(template_id)
        if template is None:
            return None
        return await self.create_handoff(template.handoff_request())


service = ShoppingListService()
