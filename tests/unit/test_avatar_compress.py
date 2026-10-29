"""Avatar compression must shrink huge data-URIs used by the live widget."""
import base64
import io

import pytest
from PIL import Image

from app.infrastructure.avatar_compress import (
    compress_avatar_bytes,
    compress_avatar_data_uri,
    bytes_to_data_uri,
)


def _big_png_data_uri(w: int = 1200, h: int = 1600) -> str:
    # Noisy pixels so PNG stays large (flat fills compress too well).
    import os

    img = Image.frombytes("RGB", (w, h), os.urandom(w * h * 3))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return bytes_to_data_uri(buf.getvalue(), "image/png")


def test_compress_bytes_produces_tiny_square():
    img = Image.new("RGB", (800, 600), (30, 40, 50))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data, mime = compress_avatar_bytes(buf.getvalue())
    assert mime in ("image/jpeg", "image/png")
    assert len(data) < 30_000
    out = Image.open(io.BytesIO(data))
    assert max(out.size) <= 64


def test_compress_data_uri_shrinks_megabyte_portrait():
    uri = _big_png_data_uri()
    assert len(uri) > 50_000
    out = compress_avatar_data_uri(uri, force=True)
    assert out is not None
    assert out.startswith("data:image/")
    assert len(out) < 40_000
    assert len(out) < len(uri) // 2


def test_small_data_uri_unchanged_without_force():
    img = Image.new("RGB", (32, 32), (1, 2, 3))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    uri = bytes_to_data_uri(buf.getvalue(), "image/jpeg")
    assert compress_avatar_data_uri(uri) == uri
