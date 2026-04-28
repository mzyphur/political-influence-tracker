from __future__ import annotations

from au_politics_money.ingest.fetch import _safe_response_headers


def test_safe_response_headers_drop_cookies_and_provider_tokens() -> None:
    headers = _safe_response_headers(
        {
            "Content-Type": "text/html",
            "ETag": '"abc"',
            "Set-Cookie": "session=secret",
            "X-Request-Id": "provider-trace",
            "Authorization": "Bearer secret",
        }
    )

    assert headers == {"Content-Type": "text/html", "ETag": '"abc"'}
