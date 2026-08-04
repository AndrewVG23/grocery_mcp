"""CLI entry point for stdio or combined HTTP service."""
from __future__ import annotations

import argparse
import os

from grocery_mcp.mcp_server import mcp


def main() -> None:
    parser = argparse.ArgumentParser(prog="grocery-mcp")
    parser.add_argument("--http", action="store_true", help="serve MCP and REST over HTTP")
    parser.add_argument("--host", default=os.environ.get("MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    args = parser.parse_args()

    if args.http:
        import uvicorn

        uvicorn.run("grocery_mcp.app:app", host=args.host, port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
