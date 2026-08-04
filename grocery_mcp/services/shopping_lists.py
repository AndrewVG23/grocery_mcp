"""Shopping-list normalization and retailer handoff orchestration."""
from __future__ import annotations

from collections import OrderedDict
from uuid import uuid4

from grocery_mcp.database import load_handoff, save_handoff
from grocery_mcp.models import (
    GroceryHandoff,
    GroceryItem,
    HandoffRequest,
    ItemResult,
    RetailerId,
    RetailerLocation,
)
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

        results: list[ItemResult] = []
        warnings = [
            (
                "This service returns direct product links only; it does not add products "
                "to the retailer cart."
            )
        ]
        for item in normalize_items(request.items):
            try:
                matches = await provider.search(item, location_id=location.id, limit=5)
            except ProviderError as exc:
                results.append(ItemResult(item=item, warning=str(exc)))
                continue
            if not matches:
                results.append(
                    ItemResult(item=item, warning="No matching products were found.")
                )
                continue

            best, *alternatives = matches
            warning = None
            if best.confidence < 0.6:
                warning = "The best match has low confidence; review alternatives."
            if best.available is False:
                warning = "The best match is currently marked out of stock."
            results.append(
                ItemResult(
                    item=item,
                    match=best,
                    alternatives=alternatives[:3],
                    warning=warning,
                )
            )

        handoff = GroceryHandoff(
            id=str(uuid4()),
            retailer=request.retailer,
            location=location,
            results=results,
            storefront_url=location.storefront_url,
            warnings=warnings,
        )
        self._handoffs[handoff.id] = handoff
        await save_handoff(handoff.id, handoff.model_dump(mode="json"))
        return handoff

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


service = ShoppingListService()
