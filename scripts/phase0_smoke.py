"""Phase 0 smoke test — verifies DB (PostGIS), Google Places, and Gemini from .env."""
import os
import sys
import httpx
import psycopg
from dotenv import load_dotenv

load_dotenv()

DB = os.environ["DATABASE_URL"].replace("postgresql+asyncpg", "postgresql")
PLACES = os.environ["GOOGLE_PLACES_API_KEY"]
GEMINI = os.environ["GEMINI_API_KEY"]

with psycopg.connect(DB) as conn:
    row = conn.execute("SELECT PostGIS_Version();").fetchone()
    print(f"[OK] postgis: {row[0]}")

r = httpx.post(
    "https://places.googleapis.com/v1/places:searchNearby",
    headers={
        "Content-Type": "application/json",
        "X-Goog-Api-Key": PLACES,
        "X-Goog-FieldMask": "places.displayName",
    },
    json={
        "includedTypes": ["restaurant"],
        "maxResultCount": 1,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": 42.9634, "longitude": -85.6681},
                "radius": 1000,
            }
        },
    },
    timeout=15,
)
r.raise_for_status()
print(f"[OK] places: {len(r.json().get('places', []))} result")

r = httpx.post(
    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI}",
    json={"contents": [{"parts": [{"text": "Reply with one word: ready"}]}]},
    timeout=30,
)
r.raise_for_status()
text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
print(f"[OK] gemini: {text!r}")

print("\nAll three OK - Phase 0 environment is ready.")
