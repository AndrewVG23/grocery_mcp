# Grocery MCP

<!-- mcp-name: io.github.AndrewVG23/grocery-mcp -->

A dedicated MCP and REST service that searches grocery retailers directly and
returns reviewable product links. It starts with:

- Kettle Range Meat Co. — Milwaukee and Elm Grove
- Outpost Natural Foods — Capitol Drive, State Street, Bay View, and Mequon

This service does **not** add products to carts, place orders, store retailer
credentials, or handle payment. Every response explicitly reports
`cart_prefilled: false`; the user opens the links, adds products, and checks out
on the retailer's own site.

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

## Tests

```bash
ruff check .
pytest
```
