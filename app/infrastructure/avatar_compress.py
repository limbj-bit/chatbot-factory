"""Compress bot avatar data-URIs so widget scripts stay small and reliable."""
from __future__ import annotations

import base64
import io
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Keep launcher/chat icons tiny; anything larger risks 414 / Render OOM / empty fallback.
TARGET_PX = 64
SOFT_MAX_DATA_URI_LEN = 24_000
HARD_RECOMPRESS_ABOVE = 20_000


def _encode_png(img) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _encode_jpeg(img, quality: int = 82) -> str:
    rgb = img.convert("RGB")
    buf = io.BytesIO()
    rgb.save(buf, format="JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def compress_avatar_bytes(raw: bytes, target_px: int = TARGET_PX) -> Tuple[bytes, str]:
    """Return (bytes, mime) for a <=target_px square avatar. Raises on failure."""
    from PIL import Image, ImageFile

    ImageFile.LOAD_TRUNCATED_IMAGES = True
    # Some mall uploads are multi-megapixel; allow decode then thumbnail.
    Image.MAX_IMAGE_PIXELS = max(getattr(Image, "MAX_IMAGE_PIXELS", 0) or 0, 200_000_000)

    img = Image.open(io.BytesIO(raw))
    img.load()
    img = img.convert("RGBA")
    img.thumbnail((target_px, target_px), Image.Resampling.LANCZOS)

    # Prefer small JPEG for photos; keep PNG if mostly transparent.
    extrema = img.split()[-1].getextrema() if img.mode == "RGBA" else (255, 255)
    has_transparency = extrema[0] < 250

    if has_transparency:
        out = io.BytesIO()
        img.save(out, format="PNG", optimize=True)
        data = out.getvalue()
        if len(data) > SOFT_MAX_DATA_URI_LEN:
            # Flatten on white and JPEG if PNG still huge
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            out2 = io.BytesIO()
            bg.save(out2, format="JPEG", quality=80, optimize=True)
            return out2.getvalue(), "image/jpeg"
        return data, "image/png"

    out = io.BytesIO()
    img.convert("RGB").save(out, format="JPEG", quality=82, optimize=True)
    return out.getvalue(), "image/jpeg"


def bytes_to_data_uri(data: bytes, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


def compress_avatar_data_uri(
    data_uri: Optional[str],
    *,
    force: bool = False,
    target_px: int = TARGET_PX,
) -> Optional[str]:
    """Compress a data-URI avatar. Returns None if input empty/unrecoverable.

    Non-data URLs are returned unchanged. Small data URIs are returned as-is
    unless force=True.
    """
    if not data_uri:
        return None
    uri = data_uri.strip()
    if not uri.startswith("data:"):
        return uri
    if not force and len(uri) <= HARD_RECOMPRESS_ABOVE:
        return uri

    try:
        comma = uri.find(",")
        if comma < 0:
            return None
        raw = base64.b64decode(uri[comma + 1 :], validate=False)
        data, mime = compress_avatar_bytes(raw, target_px=target_px)
        out = bytes_to_data_uri(data, mime)
        # Last resort: tinier JPEG
        if len(out) > SOFT_MAX_DATA_URI_LEN:
            from PIL import Image

            img = Image.open(io.BytesIO(raw)).convert("RGB")
            img.thumbnail((48, 48), Image.Resampling.LANCZOS)
            out = _encode_jpeg(img, quality=70)
        logger.info(
            "avatar_compress ok in_len=%s out_len=%s",
            len(uri),
            len(out),
        )
        return out
    except Exception as exc:
        logger.warning("avatar_compress failed in_len=%s err=%s", len(uri), exc)
        return None
