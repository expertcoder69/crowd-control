"""
test_main.py — Pytest suite for the QR Code Generation API
===========================================================
Covers:
  - Token generation (happy path, response shape)
  - QR retrieval with a valid token (status 200, image/png content type)
  - QR retrieval with an invalid token (status 404)
  - POST /qr/generate happy path (status 200, image/png, X-QR-Token header)
  - POST /qr/generate with blank data (status 400)
  - POST /qr/generate with oversized data (status 400)

Uses FastAPI's TestClient (backed by httpx) so no live server is needed.
"""

import pytest
from fastapi.testclient import TestClient

from main import app, token_store

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_store():
    """
    Reset the in-memory token store before each test.
    Without this, tokens from one test bleed into another.
    """
    token_store.clear()
    yield
    token_store.clear()


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


def test_root_returns_ok():
    """GET / should return 200 and status == 'ok'."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "qr_backend" in data


# ---------------------------------------------------------------------------
# POST /token/generate
# ---------------------------------------------------------------------------


def test_generate_token_returns_201():
    """Token generation should return 201 Created with the expected fields."""
    response = client.post("/token/generate")
    assert response.status_code == 201


def test_generate_token_response_shape():
    """Response body should contain token, created_at, and message."""
    response = client.post("/token/generate")
    body = response.json()
    assert "token" in body
    assert "created_at" in body
    assert "message" in body


def test_generate_token_is_stored():
    """Newly generated token must be persisted in the in-memory store."""
    response = client.post("/token/generate")
    token = response.json()["token"]
    assert token in token_store


def test_generate_token_uniqueness():
    """Two sequential calls must produce different tokens."""
    t1 = client.post("/token/generate").json()["token"]
    t2 = client.post("/token/generate").json()["token"]
    assert t1 != t2


# ---------------------------------------------------------------------------
# GET /qr/{token}
# ---------------------------------------------------------------------------


def test_get_qr_valid_token_returns_png():
    """A valid token should yield a 200 response with image/png content type."""
    token = client.post("/token/generate").json()["token"]
    response = client.get(f"/qr/{token}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


def test_get_qr_valid_token_non_empty_body():
    """The PNG response body must not be empty."""
    token = client.post("/token/generate").json()["token"]
    response = client.get(f"/qr/{token}")
    assert len(response.content) > 0


def test_get_qr_invalid_token_returns_404():
    """
    An unrecognised token must return 404.
    This is intentional — we don't differentiate between 'never existed'
    and 'revoked' to avoid information leakage.
    """
    response = client.get("/qr/this-token-does-not-exist")
    assert response.status_code == 404


def test_get_qr_invalid_token_error_body():
    """The 404 response should include a structured error field."""
    response = client.get("/qr/bad-token")
    body = response.json()
    assert "error" in body["detail"]
    assert "message" in body["detail"]


# ---------------------------------------------------------------------------
# POST /qr/generate
# ---------------------------------------------------------------------------


def test_post_qr_generate_returns_png():
    """POST /qr/generate with valid data should return image/png."""
    response = client.post("/qr/generate", json={"data": "https://example.com/event/42"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


def test_post_qr_generate_exposes_token_header():
    """Response must include X-QR-Token header so callers can reference the token later."""
    response = client.post("/qr/generate", json={"data": "hello-world"})
    assert "x-qr-token" in response.headers
    assert len(response.headers["x-qr-token"]) > 0


def test_post_qr_generate_token_is_stored():
    """The auto-minted token must be stored in the in-memory store."""
    response = client.post("/qr/generate", json={"data": "test-payload"})
    token = response.headers["x-qr-token"]
    assert token in token_store
    assert token_store[token]["payload"] == "test-payload"


def test_post_qr_generate_with_label():
    """Optional `label` field should be accepted and stored."""
    response = client.post(
        "/qr/generate", json={"data": "crowd-id-99", "label": "Gate A"}
    )
    assert response.status_code == 200
    token = response.headers["x-qr-token"]
    assert token_store[token]["label"] == "Gate A"


def test_post_qr_generate_blank_data_returns_400():
    """Blank or whitespace-only `data` must be rejected with 400."""
    response = client.post("/qr/generate", json={"data": "   "})
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "Invalid payload"


def test_post_qr_generate_empty_string_returns_400():
    """Empty string `data` must also be rejected with 400."""
    response = client.post("/qr/generate", json={"data": ""})
    assert response.status_code == 400


def test_post_qr_generate_oversized_data_returns_400():
    """Payloads exceeding 2500 characters must be rejected with 400."""
    oversized = "A" * 2501
    response = client.post("/qr/generate", json={"data": oversized})
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "Payload too large"


def test_get_qr_after_post_generate():
    """
    Token minted by POST /qr/generate must be usable with GET /qr/{token}.
    This validates the full round-trip lifecycle.
    """
    gen_response = client.post("/qr/generate", json={"data": "round-trip-test"})
    token = gen_response.headers["x-qr-token"]
    get_response = client.get(f"/qr/{token}")
    assert get_response.status_code == 200
    assert get_response.headers["content-type"] == "image/png"
