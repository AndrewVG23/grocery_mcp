"""Serve one Outpost checkout through the Grocery host.

The store session stays on the server. The shopper's browser opens an https
link and pays in that page. Request bodies are not logged.
"""

from __future__ import annotations

import re

import httpx
from starlette.requests import Request
from starlette.responses import HTMLResponse, Response

from grocery_mcp.outpost_checkout import load_outpost_session, save_outpost_session

_STORE_ORIGIN = "https://shop.outpost.coop"
_TEXT_MARKERS = ("html", "javascript", "json", "css", "text/", "xml")
_DROPPED_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-encoding",
    "content-length",
    "set-cookie",
    "content-security-policy",
    "content-security-policy-report-only",
    "x-frame-options",
    "strict-transport-security",
}


def shop_prefix(cart_id: str) -> str:
    return f"/outpost-cart/{cart_id}/shop"


def rewrite_store_text(text: str, prefix: str) -> str:
    rewritten = text.replace(_STORE_ORIGIN, prefix)
    rewritten = re.sub(
        rf"((?:href|src|action)=[\"'])/(?!{re.escape(prefix.lstrip('/'))})",
        rf"\1{prefix}/",
        rewritten,
        flags=re.IGNORECASE,
    )
    return re.sub(
        rf"url\(/(?!{re.escape(prefix.lstrip('/'))})",
        f"url({prefix}/",
        rewritten,
        flags=re.IGNORECASE,
    )


def _cookie_records(client: httpx.AsyncClient) -> list[dict[str, str]]:
    return [
        {
            "name": cookie.name,
            "value": cookie.value,
            "domain": cookie.domain or "shop.outpost.coop",
            "path": cookie.path or "/",
        }
        for cookie in client.cookies.jar
    ]


def _rejects_password(method: str, path: str) -> bool:
    if method.upper() not in {"POST", "PUT", "PATCH"}:
        return False
    lowered = path.lower()
    return "login" in lowered or lowered.startswith("api/auth") or "/api/auth" in f"/{lowered}"


async def proxy_outpost(cart_id: str, path: str, request: Request) -> Response:
    if not path or ".." in path or path.startswith(("/", "\\")) or "\\" in path:
        return Response("Invalid path", status_code=400)
    if _rejects_password(request.method, path):
        return HTMLResponse(
            "<p>This link is a guest cart. Sign in stays on Outpost.</p>",
            status_code=403,
        )
    session = await load_outpost_session(cart_id)
    if session is None:
        return HTMLResponse("<p>This checkout link has expired.</p>", status_code=404)

    target = f"{_STORE_ORIGIN}/{path}"
    if request.url.query:
        target = f"{target}?{request.url.query}"
    headers = {
        "User-Agent": request.headers.get("user-agent", "Mozilla/5.0"),
        "Accept": request.headers.get("accept", "*/*"),
        "Origin": _STORE_ORIGIN,
        "Referer": str(session.get("storefront_url") or f"{_STORE_ORIGIN}/"),
    }
    content_type = request.headers.get("content-type")
    if content_type:
        headers["Content-Type"] = content_type
    body = b"" if request.method.upper() in {"GET", "HEAD"} else await request.body()
    prefix = shop_prefix(cart_id)
    try:
        async with httpx.AsyncClient(timeout=40, follow_redirects=False) as client:
            for cookie in session.get("cookies") or []:
                client.cookies.set(
                    cookie["name"],
                    cookie["value"],
                    domain=cookie.get("domain") or "shop.outpost.coop",
                    path=cookie.get("path") or "/",
                )
            upstream = await client.request(
                request.method,
                target,
                headers=headers,
                content=body,
            )
            session["cookies"] = _cookie_records(client)
    except httpx.HTTPError:
        return HTMLResponse("<p>Outpost did not respond.</p>", status_code=502)
    await save_outpost_session(cart_id, session)

    media_type = upstream.headers.get("content-type", "")
    content = upstream.content
    if any(marker in media_type.lower() for marker in _TEXT_MARKERS):
        content = rewrite_store_text(content.decode("utf-8", "replace"), prefix).encode()
    response_headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() not in _DROPPED_HEADERS
    }
    location = upstream.headers.get("location")
    if location:
        if location.startswith(_STORE_ORIGIN):
            location = prefix + location.removeprefix(_STORE_ORIGIN)
        elif location.startswith("/"):
            location = prefix + location
        response_headers["location"] = location
    return Response(
        content,
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=media_type.split(";", 1)[0] or None,
    )
