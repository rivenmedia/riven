import os

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv()


X_API_KEY = os.getenv("X-API-KEY")
if not X_API_KEY:
    raise ValueError("X_API_KEY is not set")

BASE_URL = "http://localhost:8080"
HEADERS = {"x-api-key": X_API_KEY}

client = httpx.Client(base_url=BASE_URL, headers=HEADERS)


def test_secure_default_health():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"message": "True"}

def test_secure_default_rd():
    response = client.get("/api/v1/rd")
    assert response.status_code == 200
    assert "id" in response.json()

@pytest.mark.skip(reason="Optional test")
def test_secure_default_generateapikey():
    response = client.post("/api/v1/generateapikey")
    assert response.status_code == 200
    assert "message" in response.json()

def test_secure_default_services():
    response = client.get("/api/v1/services")
    assert response.status_code == 200
    assert isinstance(response.json(), dict)
    assert len(response.json()) > 0

def test_secure_default_stats():
    response = client.get("/api/v1/stats")
    assert response.status_code == 200
    assert isinstance(response.json(), dict)
    assert len(response.json()) > 0

@pytest.mark.skip(reason="Endpoint is broken")
def test_secure_default_logs():
    response = client.get("/api/v1/logs")
    assert response.status_code == 200
