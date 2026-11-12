import pytest
import respx
from httpx import Response
from starlette.requests import Request

from grocery_mcp.outpost_checkout import save_outpost_session
from grocery_mcp.outpost_proxy import proxy_outpost, rewrite_store_text


def test_rewrite_points_store_links_at_the_checkout_prefix():
    html = (
        '<base href="/s/1000-5/"/>'
        '<script src="js/app.js"></script>'
        '<a href="/s/1000-5/co">Checkout</a>'
        '{"siteUrl":"https://shop.outpost.coop/s/1000-5"}'
    )
    rewritten = rewrite_store_text(html, "/outpost-cart/abc/shop")
    assert '<base href="/outpost-cart/abc/shop/s/1000-5/"/>' in rewritten
    assert 'href="/outpost-cart/abc/shop/s/1000-5/co"' in rewritten
    assert '"siteUrl":"/outpost-cart/abc/shop/s/1000-5"' in rewritten
    assert "shop.outpost.coop" not in rewritten


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/outpost-cart/abc/shop/s/1000-5/co",
            "query_string": b"",
            "headers": [],
        }
    )


@pytest.mark.asyncio
async def test_proxy_serves_checkout_without_exposing_the_store_cookie():
    await save_outpost_session(
        "abc",
        {
            "storefront_url": "https://shop.outpost.coop/s/1000-5/",
            "cookies": [
                {
                    "name": "token",
                    "value": "guest-session",
                    "domain": "shop.outpost.coop",
                    "path": "/",
                }
            ],
        },
    )
    with respx.mock:
        respx.get("https://shop.outpost.coop/s/1000-5/co").mock(
            return_value=Response(
                200,
                headers={"content-type": "text/html", "set-cookie": "token=rotated; Path=/"},
                text='<base href="/s/1000-5/"/>Check Out',
            )
        )
        page = await proxy_outpost("abc", "s/1000-5/co", _request())
    assert page.status_code == 200
    body = page.body.decode()
    assert '<base href="/outpost-cart/abc/shop/s/1000-5/"/>' in body
    assert "Check Out" in body
    assert "set-cookie" not in {key.lower() for key in page.headers}
