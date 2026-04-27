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

USER_AGENT = (
    "AU-Politics-Money-Tracker/0.1 "
    "(public-interest research; contact: project owner)"
)

