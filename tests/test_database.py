"""Database payload decoding independent of a live PostgreSQL connection."""
from __future__ import annotations

import pytest

from grocery_mcp.database import _decode_payload


def test_decode_payload_accepts_asyncpg_json_string():
    assert _decode_payload('{"client_id":"cursor","redirect_uris":["http://localhost"]}') == {
        "client_id": "cursor",
        "redirect_uris": ["http://localhost"],
    }


def test_decode_payload_accepts_configured_json_codec_dict():
    payload = {"client_id": "cursor"}
    assert _decode_payload(payload) == payload


def test_decode_payload_preserves_null():
    assert _decode_payload(None) is None


def test_decode_payload_rejects_non_object_json():
    with pytest.raises(TypeError, match="Expected a JSON object"):
        _decode_payload('["not", "an", "object"]')
