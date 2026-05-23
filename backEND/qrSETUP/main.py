import io
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Path
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

try:
    import qrcode
    from qrcode.image.pure import PyPNGImage

    try:
        from PIL import Image
        from qrcode.image.pil import PilImage as ImageFactory

        _USING_PILLOW = True
    except ImportError:
        ImageFactory = PyPNGImage
        _USING_PILLOW = False

    _QR_AVAILABLE = True
except ImportError as exc:
    _QR_AVAILABLE = False
    _IMPORT_ERROR = str(exc)

app = FastAPI(
    title="QR Code Generation API",
    description="Generate secure tokens and render them as QR code PNG images.",
    version="1.0.0",
)

token_store: dict[str, dict] = {}


class TokenResponse(BaseModel):
    token: str
    created_at: str
    message: str


class GenerateQRRequest(BaseModel):
    data: str
    label: Optional[str] = None


class GenerateQRResponse(BaseModel):
    token: str
    message: str


def _build_qr_png(content: str) -> bytes:
    if not content:
        raise ValueError("QR content must not be empty.")

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(content)
    qr.make(fit=True)

    img = qr.make_image(image_factory=ImageFactory)

    buf = io.BytesIO()
    img.save(buf)
    buf.seek(0)
    return buf.read()


def _require_qr_libs() -> None:
    if not _QR_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "QR generation unavailable",
                "reason": "Required library not installed. Run: pip install qrcode[pil]",
            },
        )


@app.get("/", summary="Health check")
def root():
    return {
        "status": "ok",
        "qr_backend": "pillow" if _USING_PILLOW else "pypng" if _QR_AVAILABLE else "unavailable",
    }


@app.post(
    "/token/generate",
    response_model=TokenResponse,
    summary="Generate a new secure token",
    status_code=201,
)
def generate_token():
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc).isoformat()

    token_store[token] = {
        "created_at": now,
        "payload": None,
        "label": None,
    }

    return TokenResponse(
        token=token,
        created_at=now,
        message="Token created successfully. Use it with GET /qr/{token}.",
    )


@app.get(
    "/qr/{token}",
    summary="Render a QR code for an existing token",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"image/png": {}}, "description": "PNG QR code image"},
        404: {"description": "Token not found"},
        500: {"description": "Image generation failure"},
    },
)
def get_qr_for_token(
    token: str = Path(..., description="A token previously issued by POST /token/generate"),
):
    _require_qr_libs()

    record = token_store.get(token)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Token not found",
                "message": "The supplied token does not exist or has been revoked.",
            },
        )

    qr_content = token

    try:
        png_bytes = _build_qr_png(qr_content)
    except Exception:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={
                "error": "QR generation failed",
                "message": "An internal error occurred while generating the QR image.",
            },
        )

    return StreamingResponse(
        io.BytesIO(png_bytes),
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="{token[:8]}.png"'},
    )


@app.post(
    "/qr/generate",
    summary="Generate a token from a payload and return its QR code immediately",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"image/png": {}}, "description": "PNG QR code image"},
        400: {"description": "Invalid or oversized payload"},
        500: {"description": "Image generation failure"},
    },
)
def generate_qr_from_payload(body: GenerateQRRequest):
    _require_qr_libs()

    if not body.data or not body.data.strip():
        raise HTTPException(
            status_code=400,
            detail={"error": "Invalid payload", "message": "`data` must not be blank."},
        )

    MAX_PAYLOAD = 2500
    if len(body.data) > MAX_PAYLOAD:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Payload too large",
                "message": f"`data` exceeds the {MAX_PAYLOAD}-character limit for QR encoding.",
            },
        )

    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc).isoformat()
    token_store[token] = {
        "created_at": now,
        "payload": body.data,
        "label": body.label,
    }

    try:
        png_bytes = _build_qr_png(body.data)
    except Exception:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={
                "error": "QR generation failed",
                "message": "An internal error occurred while generating the QR image.",
            },
        )

    return StreamingResponse(
        io.BytesIO(png_bytes),
        media_type="image/png",
        headers={
            "Content-Disposition": 'inline; filename="qr.png"',
            "X-QR-Token": token,
            "Access-Control-Expose-Headers": "X-QR-Token",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
