import base64
import hashlib
from typing import Optional, Tuple
from fastapi import Header, HTTPException, status
from app.core.config import settings

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:  # pragma: no cover - runtime guard
    Fernet = None  # type: ignore
    InvalidToken = Exception  # type: ignore


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


def is_valid_admin_key(x_admin_key: Optional[str]) -> bool:
    """True only when the key exactly matches the configured ADMIN_API_KEY.

    Hardcoded aliases (e.g. chatbot123) are intentionally NOT accepted so a
    forgotten default cannot unlock production admin APIs.
    """
    configured = (settings.ADMIN_API_KEY or "").strip()
    if not configured or not x_admin_key:
        return False
    return x_admin_key == configured


async def verify_admin_key(x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key")) -> str:
    """Dependency for securing admin API endpoints."""
    if not is_valid_admin_key(x_admin_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Admin-Key",
        )
    return x_admin_key  # type: ignore[return-value]


def encryption_available() -> bool:
    """True if ENCRYPTION_KEY is configured and cryptography is importable."""
    return bool(settings.ENCRYPTION_KEY) and Fernet is not None


def _get_fernet() -> "Fernet":
    if Fernet is None:
        raise RuntimeError("cryptography is not installed. Install 'cryptography' to enable commerce encryption.")
    if not settings.ENCRYPTION_KEY:
        raise RuntimeError("ENCRYPTION_KEY is not configured. Commerce secret/token storage is blocked.")
    return Fernet(settings.ENCRYPTION_KEY.encode("utf-8"))


def encrypt_secret(plain: str) -> str:
    """Encrypt a secret (Client Secret / access & refresh token) with Fernet."""
    if not plain:
        return ""
    return _get_fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_secret(cipher: Optional[str]) -> Optional[str]:
    """Decrypt a Fernet ciphertext back to plaintext. Returns None on failure."""
    if not cipher:
        return None
    if not encryption_available():
        return None
    try:
        return _get_fernet().decrypt(cipher.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


def mask_secret(plain: Optional[str]) -> str:
    """Return a display-safe masked form (****last4). Never expose the full secret."""
    if not plain:
        return ""
    return "****" + plain[-4:] if len(plain) >= 4 else "****"
