import pytest
from fastapi import HTTPException
from app.core.security import compute_sha256, validate_image_file, verify_admin_key


def test_valid_jpeg_magic_bytes():
    jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01" + b"\x00" * 50
    valid, mime, err = validate_image_file(jpeg_bytes, "test.jpg", "image/jpeg")
    assert valid is True
    assert mime == "image/jpeg"
    assert err is None


def test_valid_png_magic_bytes():
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 50
    valid, mime, err = validate_image_file(png_bytes, "test.png", "image/png")
    assert valid is True
    assert mime == "image/png"
    assert err is None


def test_valid_webp_magic_bytes():
    webp_bytes = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 50
    valid, mime, err = validate_image_file(webp_bytes, "test.webp", "image/webp")
    assert valid is True
    assert mime == "image/webp"
    assert err is None


def test_fake_extension_rejected():
    fake_bytes = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00" + b"\x00" * 50  # Windows PE
    valid, mime, err = validate_image_file(fake_bytes, "malicious.jpg", "image/jpeg")
    assert valid is False
    assert "Invalid image format" in err


def test_oversized_file_rejected():
    huge_bytes = b"\xff\xd8\xff" + (b"0" * (11 * 1024 * 1024))  # 11MB
    valid, mime, err = validate_image_file(huge_bytes, "huge.jpg", "image/jpeg")
    assert valid is False
    assert "exceeds limit" in err


def test_sha256_hash():
    data = b"fresh_strawberry_claim_image"
    hash_val = compute_sha256(data)
    assert len(hash_val) == 64
    assert hash_val == compute_sha256(data)


@pytest.mark.asyncio
async def test_admin_key_verification():
    # Valid key
    valid_key = await verify_admin_key(x_admin_key="admin-dev-secret-key-change-in-prod")
    assert valid_key == "admin-dev-secret-key-change-in-prod"

    # Invalid key
    with pytest.raises(HTTPException) as exc:
        await verify_admin_key(x_admin_key="wrong-key")
    assert exc.value.status_code == 401
