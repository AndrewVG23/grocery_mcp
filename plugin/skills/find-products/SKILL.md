---
name: find-products
description: Search Kettle Range and Outpost and start a cart the shopper pays for on the store site. Use when the user wants product links or a pickup cart. Do not take a card number.
---

# Find products

Answer from Grocery MCP. Name the retailer and the products. The shopper pays on the retailer site.

## Steps

1. Call `find_grocery_retailers` when the store location is not already known.
2. Call `search_grocery_products` for a single product, or `start_grocery_checkout` for a list that should open a cart.
3. Give the shopper `checkout_url`. Say the order is not placed until they finish checkout on that page.
4. Show unmatched items, prices, and availability from the tool. Do not swap in a different kind of product to force a match.

## Limits

This server does not take a card number or a retailer password. Do not say the order is placed when the tool has only returned a link.
