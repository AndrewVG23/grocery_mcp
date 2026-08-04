"""REST API routes for grocery catalog handoffs."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from grocery_mcp import __version__
from grocery_mcp.models import GroceryHandoff, HandoffRequest, ProductMatch, RetailerLocation
from grocery_mcp.providers.base import ProviderError
from grocery_mcp.services.shopping_lists import service

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "grocery-mcp", "version": __version__}


@router.get("/v1/retailers", response_model=list[RetailerLocation])
async def retailers() -> list[RetailerLocation]:
    return await service.retailers()


@router.get("/v1/products/search", response_model=list[ProductMatch])
async def search_products(
    retailer: str,
    query: str,
    location_id: str | None = None,
    limit: int = 5,
) -> list[ProductMatch]:
    try:
        from grocery_mcp.models import GroceryItem, RetailerId

        return await service.search(
            RetailerId(retailer),
            GroceryItem(name=query),
            location_id=location_id,
            limit=min(max(limit, 1), 10),
        )
    except (ValueError, ProviderError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/v1/handoffs", response_model=GroceryHandoff, status_code=201)
async def create_handoff(request: HandoffRequest) -> GroceryHandoff:
    try:
        return await service.create_handoff(request)
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/v1/handoffs/{handoff_id}", response_model=GroceryHandoff)
async def get_handoff(handoff_id: str) -> GroceryHandoff:
    handoff = await service.get_handoff(handoff_id)
    if handoff is None:
        raise HTTPException(status_code=404, detail="handoff not found")
    return handoff
