"""Combined REST and streamable HTTP MCP application."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from grocery_mcp.api import router
from grocery_mcp.database import close_pool
from grocery_mcp.mcp_server import mcp

mcp_app = mcp.http_app(path="/mcp")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp_app.lifespan(app):
        try:
            yield
        finally:
            await close_pool()


app = FastAPI(
    title="Grocery MCP",
    description="Direct Kettle Range and Outpost product-link handoffs",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)
# Mount last so REST routes are matched before FastMCP's root-level OAuth routes.
app.mount("/", mcp_app)
