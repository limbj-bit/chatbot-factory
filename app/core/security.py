import base64
import hashlib
import time
from collections import defaultdict, deque
from typing import Callable, Optional, Tuple
from fastapi import Header, HTTPException, Request, status
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


def _is_heic(content: bytes, filename: str, declared_mime: str) -> bool:
    name = (filename or "").lower()
    mime = (declared_mime or "").lower()
    if name.endswith((".heic", ".heif")):
        return True
    if mime in ("image/heic", "image/heif", "image/heic-sequence", "image/heif-sequence"):
        return True
    # ISO BMFF: bytes 4..12 == "ftyp" + brand
    if len(content) >= 12 and content[4:8] == b"ftyp":
        brand = content[8:12].lower()
        if brand in (b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"):
            return True
    return False


def normalize_uploaded_image(
    content: bytes, filename: str, declared_mime: str
) -> Tuple[bytes, str, Optional[str]]:
    """Convert HEIC/HEIF to JPEG when possible; otherwise pass-through.

    Returns (bytes, mime, error). On conversion failure returns original bytes
    so the caller's magic-byte validation can reject it cleanly.
    """
    if not _is_heic(content, filename, declared_mime):
        return content, declared_mime, None
    try:
        import io

        import pillow_heif
        from PIL import Image

        pillow_heif.register_heif_opener()
        img = Image.open(io.BytesIO(content))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue(), "image/jpeg", None
    except Exception as exc:  # pragma: no cover - depends on libheif
        return content, declared_mime, f"HEIC/HEIF conversion failed: {exc}"


def extract_image_metadata(content: bytes) -> dict:
    """Best-effort EXIF + dimensions extraction for fraud defense/audit."""
    try:
        import io

        from PIL import Image
        from PIL.ExifTags import TAGS

        img = Image.open(io.BytesIO(content))
        meta = {"width": img.width, "height": img.height, "format": img.format}
        exif = getattr(img, "getexif", None)
        exif_obj = exif() if callable(exif) else None
        if exif_obj:
            for tag_id, value in exif_obj.items():
                name = TAGS.get(tag_id, str(tag_id))
                if name in (
                    "Make",
                    "Model",
                    "DateTimeOriginal",
                    "DateTime",
                    "Software",
                    "LensModel",
                ):
                    meta[name] = str(value)
        return meta
    except Exception:
        return {}


def compute_perceptual_hash(content: bytes, size: int = 8) -> Optional[str]:
    """Average-hash (aHash) for near-duplicate detection; no extra deps."""
    try:
        import io

        from PIL import Image

        img = Image.open(io.BytesIO(content)).convert("L").resize((size, size))
        pixels = list(img.getdata())
        avg = sum(pixels) / len(pixels)
        bits = "".join("1" if p > avg else "0" for p in pixels)
        return format(int(bits, 2), "x").zfill(size * size // 4)
    except Exception:
        return None


def ai_generated_suspicion(metadata: dict) -> int:
    """Heuristic 0-100 suspicion score for AI-generated/edited photos.

    v1: based on missing camera EXIF and editing software hints. This is a
    triage signal only; high scores route the claim to manual review.
    """
    if not isinstance(metadata, dict):
        return 0
    score = 0
    if not metadata.get("Make"):
        score += 20
    if not metadata.get("Model"):
        score += 15
    if not metadata.get("DateTimeOriginal") and not metadata.get("DateTime"):
        score += 15
    software = str(metadata.get("Software") or "").lower()
    if any(tok in software for tok in ("photoshop", "gimp", "canva", "midjourney", "dall", "stable diffusion")):
        score += 30
    return min(100, score)


def hamming_distance(a: Optional[str], b: Optional[str]) -> int:
    if not a or not b or len(a) != len(b):
        return 64
    try:
        return bin(int(a, 16) ^ int(b, 16)).count("1")
    except ValueError:
        return 64


# Simple in-memory rate limiter (per-process; sufficient for single-instance hardening).
_RATE_BUCKETS: dict = defaultdict(deque)


def check_rate_limit(key: str, limit: int, window_sec: int) -> None:
    now = time.time()
    bucket = _RATE_BUCKETS[key]
    while bucket and bucket[0] < now - window_sec:
        bucket.popleft()
    if len(bucket) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please retry later.",
        )
    bucket.append(now)


def rate_limiter(limit: int = 60, window_sec: int = 60) -> Callable:
    async def _dep(request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        check_rate_limit(f"{request.url.path}:{client}", limit, window_sec)

    return _dep


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
