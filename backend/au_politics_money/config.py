from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(
    os.environ.get("AUPOL_PROJECT_ROOT", Path(__file__).resolve().parents[2])
).resolve()

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
AUDIT_DIR = DATA_DIR / "audit"

USER_AGENT = os.environ.get("AUPOL_USER_AGENT") or (
    "AU-Politics-Money-Tracker/0.1 "
    "(public-interest research; contact: mzyphur@instats.org)"
)

BROWSER_COMPATIBLE_USER_AGENT = os.environ.get("AUPOL_BROWSER_COMPATIBLE_USER_AGENT") or (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 "
    "AU-Politics-Money-Tracker/0.1 "
    "(public-interest research; contact: mzyphur@instats.org)"
)

API_CORS_ALLOW_ORIGINS = tuple(
    origin.strip()
    for origin in os.environ.get(
        "AUPOL_API_CORS_ALLOW_ORIGINS",
        "http://127.0.0.1:8008,http://localhost:8008,"
        "http://127.0.0.1:5173,http://localhost:5173,"
        "http://127.0.0.1:3000,http://localhost:3000",
    ).split(",")
    if origin.strip()
)

API_RATE_LIMIT_PER_MINUTE = int(os.environ.get("AUPOL_API_RATE_LIMIT_PER_MINUTE", "120"))
API_MIN_FREE_TEXT_QUERY_LENGTH = int(os.environ.get("AUPOL_API_MIN_FREE_TEXT_QUERY_LENGTH", "3"))
