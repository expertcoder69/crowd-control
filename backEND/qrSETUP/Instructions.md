# QR Setup — Instructions

## Overview

FastAPI service that generates secure one-time tokens and renders them as QR code PNG images.

## Prerequisites

- Python **3.11+**
- `pip`

## Setup

```bash
cd backEND/qrSETUP

# Create and activate a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Running the Server

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The server starts at **http://localhost:8000**.

### Interactive API Docs

| UI | URL |
|----|-----|
| Swagger UI | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |

## API Reference

### `GET /`
Health check. Returns server status and the active QR image backend (`pillow` or `pypng`).

### `POST /token/generate`
Mints a cryptographically secure token and stores it in memory.

**Response (201)**
```json
{
  "token": "<url-safe token>",
  "created_at": "2024-01-01T00:00:00+00:00",
  "message": "Token created successfully. Use it with GET /qr/{token}."
}
```

### `GET /qr/{token}`
Streams a PNG QR code for a previously generated token.

| Status | Meaning |
|--------|---------|
| 200 | `image/png` body |
| 404 | Token not found |
| 503 | QR library unavailable |
| 500 | Image generation error |

### `POST /qr/generate`
One-shot endpoint: accepts a payload, mints a token, and streams the QR code PNG immediately.

**Request body**
```json
{
  "data": "https://example.com/event/42",
  "label": "Gate A"
}
```

| Field | Type | Required | Limit |
|-------|------|----------|-------|
| `data` | string | yes | ≤ 2500 characters |
| `label` | string | no | — |

**Response headers**

- `X-QR-Token` — the auto-minted token, usable with `GET /qr/{token}`.

| Status | Meaning |
|--------|---------|
| 200 | `image/png` body |
| 400 | Blank or oversized `data` |
| 503 | QR library unavailable |
| 500 | Image generation error |

## Running the Tests

```bash
# From backEND/qrSETUP with the virtual environment active
pytest test_main.py -v
```

### What the test suite covers

| Test | Description |
|------|-------------|
| `test_root_returns_ok` | Health check returns 200 and `status == "ok"` |
| `test_generate_token_returns_201` | Token creation returns 201 |
| `test_generate_token_response_shape` | Response body has `token`, `created_at`, `message` |
| `test_generate_token_is_stored` | Token is persisted in the in-memory store |
| `test_generate_token_uniqueness` | Sequential calls produce unique tokens |
| `test_get_qr_valid_token_returns_png` | Valid token yields `image/png` |
| `test_get_qr_valid_token_non_empty_body` | PNG body is non-empty |
| `test_get_qr_invalid_token_returns_404` | Unknown token returns 404 |
| `test_get_qr_invalid_token_error_body` | 404 body contains structured error |
| `test_post_qr_generate_returns_png` | POST /qr/generate returns `image/png` |
| `test_post_qr_generate_exposes_token_header` | `X-QR-Token` header is present |
| `test_post_qr_generate_token_is_stored` | Minted token is in store with correct payload |
| `test_post_qr_generate_with_label` | Optional `label` is stored |
| `test_post_qr_generate_blank_data_returns_400` | Blank data → 400 |
| `test_post_qr_generate_empty_string_returns_400` | Empty string → 400 |
| `test_post_qr_generate_oversized_data_returns_400` | > 2500 chars → 400 |
| `test_get_qr_after_post_generate` | Round-trip: POST then GET returns valid PNG |

### Quick smoke test (no pytest)

```bash
# Terminal 1 — start the server
uvicorn main:app --port 8000

# Terminal 2 — mint a token, then fetch its QR code
TOKEN=$(curl -s -X POST http://localhost:8000/token/generate | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
curl -o qr.png http://localhost:8000/qr/$TOKEN
open qr.png   # macOS; use `xdg-open qr.png` on Linux
```

## Notes

- The in-memory `token_store` is **not persisted** across restarts. For production use, replace it with a TTL-aware store such as Redis.
- QR images are streamed directly from memory — no temporary files are written to disk.
- Stack traces are printed to the server console only; clients receive only safe generic error messages.
