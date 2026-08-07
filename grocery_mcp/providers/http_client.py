"""Shared HTTP client for retailer storefront calls."""
from __future__ import annotations

import httpx

from grocery_mcp.config import request_timeout

_SHARED: httpx.AsyncClient | None = None


def storefront_client() -> httpx.AsyncClient:
    global _SHARED
    if _SHARED is None:
        _SHARED = httpx.AsyncClient(
            timeout=request_timeout(),
            follow_redirects=True,
            headers={"User-Agent": "grocery-mcp/0.1 (+catalog-link-service)"},
        )
    return _SHARED
