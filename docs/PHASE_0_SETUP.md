# Phase 0 — Setup

Execution-oriented setup guide for the local development environment of **Broken Lunch GR**. Every step has a verification command. Run in order.

## Overview

- **Goal:** bring the local machine to a state where Phase 1 (backend scaffolding) can start immediately.
- **Estimated time:** 20–40 minutes.
- **Environment assumed:** Windows 11, PowerShell, Docker Desktop running, Python 3.11+ installed, Git installed.
- **Deferred to later phase:** DigitalOcean account, Managed PostgreSQL, Spaces bucket, Android Studio / SDK. These are NOT required for Phase 0.

Prerequisite checklist:

- [ ] Google Cloud project with billing enabled
- [ ] Google Places API (New) enabled
- [ ] Gemini API key from Google AI Studio
- [ ] Docker Desktop running (`docker ps` works)
- [ ] Python 3.11+ installed (`py -3.11 --version` works)

---

## Step 1 — Environment Verification

Confirm all baseline tools are present and at acceptable versions.

**Commands (PowerShell):**
```powershell
py -3.11 --version
docker --version
docker ps
git --version
```

**Verify:** Python ≥ 3.11, Docker Engine responding (no error on `docker ps`), Git any recent version.

If Python 3.11 is missing: install from https://www.python.org/downloads/ (check "Add to PATH").
If Docker is not running: open Docker Desktop and wait until the whale icon is steady.

---

## Step 2 — Project Workspace Check

Confirm the repo layout is as expected.

**Commands:**
```powershell
cd C:\Users\aa\Hackfest_SunghunKim
git status
ls docs
```

**Verify:** `docs/` contains the 6 design docs (`MASTER_DESIGN.md`, `CLAUDE_CODE_TASKS.md`, `SCHEMA.sql`, `API.md`, `GEMINI_PROMPTS.md`, `DESIGN_SPEC.md`). Working tree otherwise clean.

---

## Step 3 — Create Root `.env` and `.env.example`

Create the environment file the backend will read, plus a committed template.

**Write `.env.example`** (committed, no secrets):
```
# Database
DATABASE_URL=postgresql+asyncpg://postgres:dev@localhost:5432/broken_lunch

# Google APIs
GOOGLE_PLACES_API_KEY=
GEMINI_API_KEY=

# Misc
ENV=local
```

**Write `.env`** (NOT committed — same keys, filled values. Placeholders until Steps 4 & 5).

**Verify:**
```powershell
Test-Path .env
Test-Path .env.example
```
Both must return `True`.

---

## Step 4 — Register & Verify Google Places API Key

⏸  **PAUSE if running fresh:** ask the user for `GOOGLE_PLACES_API_KEY`.

Paste the value into `.env` under `GOOGLE_PLACES_API_KEY=`.

**Verification (PowerShell):**
```powershell
$key = (Get-Content .env | Select-String 'GOOGLE_PLACES_API_KEY=').ToString().Split('=')[1]
curl.exe -s -X POST "https://places.googleapis.com/v1/places:searchNearby" `
  -H "Content-Type: application/json" `
  -H "X-Goog-Api-Key: $key" `
  -H "X-Goog-FieldMask: places.displayName" `
  -d '{\"includedTypes\":[\"restaurant\"],\"maxResultCount\":3,\"locationRestriction\":{\"circle\":{\"center\":{\"latitude\":42.9634,\"longitude\":-85.6681},\"radius\":1000}}}'
```

**Verify:** response body contains a `places` array with at least one restaurant. HTTP 200.

If you see `PERMISSION_DENIED` → enable Places API (New) in Google Cloud Console and ensure billing is active.

---

## Step 5 — Register & Verify Gemini API Key

⏸  **PAUSE if running fresh:** ask the user for `GEMINI_API_KEY`.

Paste into `.env` under `GEMINI_API_KEY=`.

**Verification (PowerShell):**
```powershell
$key = (Get-Content .env | Select-String 'GEMINI_API_KEY=').ToString().Split('=')[1]
curl.exe -s "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=$key" `
  -H "Content-Type: application/json" `
  -d '{\"contents\":[{\"parts\":[{\"text\":\"Reply with the single word: ready\"}]}]}'
```

**Verify:** response contains `"text": "ready"` (or near-equivalent). HTTP 200.

If `API_KEY_INVALID` → regenerate at https://aistudio.google.com/apikey.

---

## Step 6 — Launch Local PostGIS Container

Start PostgreSQL 16 with PostGIS 3.4 via Docker.

**Command:**
```powershell
docker run -d `
  --name broken-lunch-db `
  -e POSTGRES_USER=postgres `
  -e POSTGRES_PASSWORD=dev `
  -e POSTGRES_DB=broken_lunch `
  -p 5432:5432 `
  -v broken_lunch_pgdata:/var/lib/postgresql/data `
  postgis/postgis:16-3.4
```

**Verify:**
```powershell
docker ps --filter name=broken-lunch-db --format "{{.Status}}"
```
Must show `Up ...` (not `Restarting`, not empty).

Wait ~10 seconds for the DB to finish initializing, then:
```powershell
docker exec broken-lunch-db pg_isready -U postgres
```
Expect `accepting connections`.

---

## Step 7 — Enable PostGIS Extension

PostgreSQL is running; now enable the PostGIS extension inside the `broken_lunch` database.

**Command:**
```powershell
docker exec -it broken-lunch-db psql -U postgres -d broken_lunch -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

**Verify:**
```powershell
docker exec -it broken-lunch-db psql -U postgres -d broken_lunch -c "SELECT PostGIS_Version();"
```
Must print a version line (e.g. `3.4 USE_GEOS=1 USE_PROJ=1 USE_STATS=1`).

---

## Step 8 — Python Virtual Environment

Create and activate the venv that Phase 1 will populate.

**Commands:**
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install "httpx>=0.27" "psycopg[binary]>=3.1" "python-dotenv>=1.0"
```

**Verify:**
```powershell
python -c "import sys; print(sys.executable)"
```
Must print a path inside `...\.venv\Scripts\`.

If `Activate.ps1` is blocked: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` (one-time).

---

## Step 9 — Smoke Test (`scripts/phase0_smoke.py`)

One script that pings all three external dependencies: Postgres + PostGIS, Google Places, Gemini.

**Create `scripts/phase0_smoke.py`:**
```python
import os, sys, httpx, psycopg
from dotenv import load_dotenv

load_dotenv()

DB = os.environ["DATABASE_URL"].replace("postgresql+asyncpg", "postgresql")
PLACES = os.environ["GOOGLE_PLACES_API_KEY"]
GEMINI = os.environ["GEMINI_API_KEY"]

# 1. Postgres + PostGIS
with psycopg.connect(DB) as conn:
    v = conn.execute("SELECT PostGIS_Version();").fetchone()[0]
    print(f"[OK] postgis: {v}")

# 2. Places
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
            "circle": {"center": {"latitude": 42.9634, "longitude": -85.6681}, "radius": 1000}
        },
    },
    timeout=15,
)
r.raise_for_status()
print(f"[OK] places: {len(r.json().get('places', []))} result")

# 3. Gemini
r = httpx.post(
    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI}",
    json={"contents": [{"parts": [{"text": "Reply with one word: ready"}]}]},
    timeout=30,
)
r.raise_for_status()
text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
print(f"[OK] gemini: {text!r}")

print("\nAll three OK — Phase 0 environment is ready.")
```

**Run:**
```powershell
python scripts\phase0_smoke.py
```

**Verify:** three `[OK]` lines and the final "ready" message.

---

## Step 10 — Harden `.gitignore`

Ensure secrets and local artefacts never get committed.

**Append (or create) `.gitignore`:**
```
.env
.venv/
__pycache__/
*.pyc
*.sqlite
*.db
.DS_Store
.idea/
.vscode/
```

**Verify:**
```powershell
git status
git check-ignore .env .venv
```
`.env` and `.venv` must NOT show under "Untracked files" and `git check-ignore` must echo them back.

---

## Step 11 — Readiness Summary

Final state check. Copy-paste the following block and confirm every bullet:

```
[ ] docs/ contains 6 design documents
[ ] .env exists (gitignored), .env.example committed
[ ] Google Places API key validated (Step 4)
[ ] Gemini API key validated (Step 5)
[ ] PostGIS container "broken-lunch-db" running on :5432
[ ] PostGIS extension enabled in "broken_lunch" database
[ ] .venv created and activated
[ ] scripts/phase0_smoke.py passes with 3x [OK]
[ ] .gitignore hardened (.env, .venv not tracked)
```

**Deferred to Phase 1+:**
- DigitalOcean account + $200 credit
- Managed PostgreSQL (production)
- Spaces bucket (image storage)
- Android Studio / SDK
- GitHub repo naming (`broken-lunch-gr`) — current repo is `Hackfest_SunghunKim`, decide later whether to rename or keep

When every box above is checked, Phase 0 is complete. Proceed to `CLAUDE_CODE_TASKS.md` → Task 1.1 (FastAPI scaffolding).
