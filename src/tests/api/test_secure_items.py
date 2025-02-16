import os

import httpx

# import pytest
from dotenv import load_dotenv

load_dotenv()


X_API_KEY = os.getenv("X-API-KEY")
if not X_API_KEY:
    raise ValueError("X_API_KEY is not set")

BASE_URL = "http://localhost:8080"
HEADERS = {"x-api-key": X_API_KEY}

client = httpx.Client(base_url=BASE_URL, headers=HEADERS)


def test_secure_items_states():
    response = client.get("/api/v1/items/states")
    assert response.status_code == 200
    assert isinstance(response.json(), dict)
    assert len(response.json()) > 0
    assert "success" in response.json()
