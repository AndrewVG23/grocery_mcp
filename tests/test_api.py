import pytest
from fastapi.testclient import TestClient

from grocery_mcp.app import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_retailers_lists_both_providers(client):
    response = client.get("/v1/retailers")
    assert response.status_code == 200
    retailers = {item["retailer"] for item in response.json()}
    assert retailers == {"kettle_range", "outpost"}
