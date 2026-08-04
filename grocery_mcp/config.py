"""Environment-driven service configuration."""
from __future__ import annotations

import os


def request_timeout() -> float:
    return float(os.environ.get("STOREFRONT_TIMEOUT", "15"))


def cache_ttl_seconds() -> int:
    return int(os.environ.get("CATALOG_CACHE_TTL", "300"))


def public_base_url() -> str | None:
    explicit = os.environ.get("PUBLIC_BASE_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
    if domain:
        return f"https://{domain}"
    return None


def mcp_auth_enabled() -> bool:
    disabled = os.environ.get("MCP_DISABLE_AUTH", "").strip().lower()
    if disabled in {"1", "true", "yes"}:
        return False
    required = os.environ.get("MCP_REQUIRE_AUTH", "").strip().lower()
    if required in {"1", "true", "yes"}:
        return True
    return public_base_url() is not None
