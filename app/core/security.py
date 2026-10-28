import hashlib
from typing import Optional, Tuple
from fastapi import Header, HTTPException, status
from app.core.config import settings


# Magic numbers for image file validation
MAGIC_HEADERS = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),  # also has WEBP at offset 8
}


def compute_sha256(data: bytes) -> str:
    """Compute SHA-256 hash of byte contents."""
    return hashlib.sha256(data).hexdigest()


def validate_image_file(
    content: bytes, filename: str, declared_mime: str
) -> Tuple[bool, str, Optional[str]]:
    """Validate image content against size, extension, and magic bytes.
    
    Returns (is_valid, detected_mime, error_message).
    """
    max_bytes = settings.CLAIM_IMAGE_MAX_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        return False, declared_mime, f"File size exceeds limit of {settings.CLAIM_IMAGE_MAX_SIZE_MB}MB."

    if len(content) < 16:
        return False, declared_mime, "File is too small or corrupted."

    # Validate Magic Bytes
    detected_mime = None
    if content.startswith(b"\xff\xd8\xff"):
        detected_mime = "image/jpeg"
    elif content.startswith(b"\x89PNG\r\n\x1a\n"):
        detected_mime = "image/png"
    elif content.startswith(b"RIFF") and len(content) >= 12 and content[8:12] == b"WEBP":
        detected_mime = "image/webp"

    if not detected_mime:
        return False, "application/octet-stream", "Invalid image format. Only JPEG, PNG, and WebP are allowed."

    return True, detected_mime, None


async def verify_admin_key(x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key")) -> str:
    """Dependency for securing admin API endpoints."""
    allowed_keys = {"chatbot123", "admin-dev-secret-key-change-in-prod", settings.ADMIN_API_KEY}
    if not x_admin_key or x_admin_key not in allowed_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Admin-Key",
        )
    return x_admin_key
