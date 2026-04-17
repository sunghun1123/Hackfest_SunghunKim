# Broken Lunch GR — Backend

FastAPI + SQLAlchemy (async) + PostgreSQL/PostGIS.

## Local run

From the repository root, with the shared virtual environment already
created by Phase 0:

```powershell
# 1. activate the venv
.\.venv\Scripts\Activate.ps1

# 2. enter backend and start the API
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Then:

- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

`app.config.Settings` reads `backend/.env` (see `.env.example`). A
working Phase 0 `.env` supplies `DATABASE_URL`, `GOOGLE_PLACES_API_KEY`,
and `GEMINI_API_KEY`.

## Dependencies

`requirements.txt` is generated via `pip freeze` from the project-root
`.venv`. On Windows the crawler path substitutes `protego` for `reppy`
(the latter needs MSVC to build) and defers `pdf2image` to Task 1.4
(needs the poppler binary).
