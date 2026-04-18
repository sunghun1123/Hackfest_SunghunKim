"""Shared pytest config. Ensures `backend/` is on sys.path when tests are
invoked from the repo root with `pytest backend/tests` (no installed package)."""

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Unit tests never need real API keys / DB. Populate placeholders so that
# `from app.config import settings` does not blow up Settings validation.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("GOOGLE_PLACES_API_KEY", "test")
os.environ.setdefault("GEMINI_API_KEY", "test")
