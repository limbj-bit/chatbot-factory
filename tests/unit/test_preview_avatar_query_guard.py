"""Showroom must not put data: / huge avatars into widget script query strings."""


def avatar_url_safe_for_query(url: str, max_len: int = 1800) -> str:
    """Mirror of static/index.html avatarUrlSafeForQuery."""
    if not url:
        return ""
    if url.startswith("data:"):
        return ""
    if len(url) > max_len:
        return ""
    return url


def test_data_uri_never_goes_in_query():
    huge = "data:image/png;base64," + ("A" * 500_000)
    assert avatar_url_safe_for_query(huge) == ""


def test_short_https_avatar_allowed():
    url = "https://cdn.example.com/avatar.png"
    assert avatar_url_safe_for_query(url) == url


def test_oversized_https_rejected():
    url = "https://cdn.example.com/" + ("x" * 2000)
    assert avatar_url_safe_for_query(url) == ""
