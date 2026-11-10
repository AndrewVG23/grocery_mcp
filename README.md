# Grocery MCP

<!-- mcp-name: io.github.AndrewVG23/grocery-mcp -->

A dedicated MCP and REST service that searches grocery retailers directly and
returns reviewable product links. It starts with:

- Kettle Range Meat Co. — Milwaukee and Elm Grove
- Outpost Natural Foods — Capitol Drive, State Street, Bay View, and Mequon

This service does **not** add products to carts, place orders, store retailer
credentials, or handle payment. Every response reports `cart_prefilled: false`.
The shopper opens the links and checks out on the retailer's own site.

A Kettle Range link opened in the shopper's browser stays in that store session,
on the product page. An Outpost link opened from Claude starts a new visit,
because Outpost does not send its session cookie on a click from another site.
Paste Outpost links into a tab that is already on the Outpost storefront.

## Connect

Hosted server:

```text
https://grocery-mcp-production.up.railway.app/mcp
```

Claude and ChatGPT sign the person in. There is no shared password.

- [Add Grocery in Claude](https://claude.ai/customize/connectors?modal=add-custom-connector&connectorName=Grocery&connectorUrl=https%3A%2F%2Fgrocery-mcp-production.up.railway.app%2Fmcp)
- ChatGPT, on a Business, Enterprise, or Edu workspace: open [chatgpt.com/plugins](https://chatgpt.com/plugins), choose **Add custom MCP server**, paste the URL, and use **OAuth**.

Start with `find_grocery_retailers`, then search or hand off a list. The client must open `browser_session.start_url` in the person's own browser, then open each product link in that same browser so Add to cart hits one cart. `cart_prefilled` stays false.

Prices and stock come from the store's public site at the moment of the search. Kettle Range covers Milwaukee and Elm Grove. Outpost covers Capitol Drive, State Street, Bay View, and Mequon.

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run

```bash
python -m grocery_mcp.server
python -m grocery_mcp.server --http
```

HTTP endpoints:

- MCP: `http://localhost:8080/mcp`
- Health: `http://localhost:8080/health`
- OpenAPI: `http://localhost:8080/docs`
- Retailers: `http://localhost:8080/v1/retailers`
- Product search: `http://localhost:8080/v1/products/search`
- Handoffs: `POST http://localhost:8080/v1/handoffs`

When `DATABASE_URL` is configured, handoffs and OAuth dynamic client
registrations are persisted in PostgreSQL. Without it, local development uses
process memory.

## MCP tools

- `find_grocery_retailers`
- `search_grocery_products`
- `create_grocery_handoff`
- `get_grocery_handoff`
- `create_grocery_order_template`
- `list_grocery_order_templates`
- `create_handoff_from_template`

Example handoff input:

```json
{
  "retailer": "kettle_range",
  "location_id": "milwaukee",
  "items": [
    {"name": "boneless chicken thighs", "quantity": 2, "unit": "lb"},
    {"name": "ground beef", "quantity": 1, "unit": "lb"}
  ]
}
```

## Data behavior

Product names, prices, availability, and links come from each retailer's
public customer storefront at request time. These storefront interfaces are
not formal partner APIs and can change without notice. Responses include match
confidence, alternatives, and observation timestamps so clients can make this
uncertainty visible.

Matching requires strong token overlap, rejects obvious cross-category
substitutions, and prefers available products. If no safe result exists, the
item is explicitly unmatched rather than replaced with a loosely related item.

Reusable templates persist the retailer, location, and normalized grocery
items. Running a template always performs fresh catalog searches and creates a
new review-only handoff.

## Directory listings

Registry name: `io.github.AndrewVG23/grocery-mcp`.

| Step | Action |
| --- | --- |
| Official MCP Registry | Tag `v0.1.1` (see `publish-mcp` workflow) |
| [Glama](https://glama.ai/mcp/servers) | Claim GitHub repo; hosted URL tab → `https://grocery-mcp-production.up.railway.app/mcp` |
| [Smithery](https://smithery.ai/new) | External HTTP → same MCP URL (OAuth) |
| [mcp.so](https://mcp.so/submit) | Submit repo `https://github.com/AndrewVG23/grocery_mcp` or the MCP URL |

Server card: `https://grocery-mcp-production.up.railway.app/.well-known/mcp/server-card.json`

## Tests

```bash
ruff check .
pytest
```
