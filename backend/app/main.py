from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import engine, get_db
from app.routers import restaurants


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Auto-detect PostGIS: set settings.postgis_enabled so routers pick the
    # right query path. If detection fails we stay in Plan B (safer default).
    try:
        async with engine.connect() as conn:
            res = await conn.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'postgis'")
            )
            settings.postgis_enabled = res.scalar() is not None
    except Exception:
        settings.postgis_enabled = False
    yield
    await engine.dispose()


app = FastAPI(title="Broken Lunch GR API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(restaurants.router)


@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> dict:
    db_ok = False
    try:
        result = await db.execute(text("SELECT 1"))
        db_ok = result.scalar() == 1
    except Exception:
        db_ok = False
    return {
        "status": "ok",
        "env": settings.env,
        "db": db_ok,
        "postgis_enabled": settings.postgis_enabled,
    }
