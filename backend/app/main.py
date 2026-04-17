from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import engine, get_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(title="Broken Lunch GR API", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> dict:
    db_ok = False
    try:
        result = await db.execute(text("SELECT 1"))
        db_ok = result.scalar() == 1
    except Exception:
        db_ok = False
    return {"status": "ok", "env": settings.env, "db": db_ok}
