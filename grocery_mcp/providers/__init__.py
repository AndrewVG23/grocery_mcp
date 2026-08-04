"""Retailer catalog adapters."""

from grocery_mcp.providers.kettle_range import KettleRangeProvider
from grocery_mcp.providers.outpost import OutpostProvider

__all__ = ["KettleRangeProvider", "OutpostProvider"]
