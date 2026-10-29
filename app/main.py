import asyncio
from typing import Any, Awaitable, Callable

import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi_pagination import add_pagination
from redis import asyncio as aioredis
from sqlalchemy import text

from app.api import api_v1, api_login
from app.config.config import settings
from app.database import async_session
from app.sockets.sockets import sio_app

app = FastAPI()

add_pagination(app)


origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter()
api_router.include_router(api_v1.api_router_v1, tags=["api_v1"])
api_router_login = APIRouter()
api_router_login.include_router(api_login.api_router_login, tags=["api_login"])


app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(api_router_login, prefix=settings.API_LOGIN_STR)

@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict:
    try:
        async with async_session() as db:
            await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=2)
    except Exception:
        raise HTTPException(status_code=503, detail="database unreachable")
    return {"status": "ready"}


_CHECK_TIMEOUT_SECONDS = 2


async def check_database() -> None:
    """Raise on failure: single round-trip proving the database answers."""
    async with async_session() as db:
        await db.execute(text("SELECT 1"))


async def check_redis() -> None:
    """Raise on failure: PING over a short-lived client."""
    client = aioredis.from_url(settings.REDIS_URI)
    try:
        await client.ping()
    finally:
        await client.aclose()


@app.get("/livez")
async def liveness() -> dict:
    """Liveness probe target: always 200 while the process runs."""
    return {"status": "ok"}


@app.get("/readyz")
async def readiness() -> JSONResponse:
    """Readiness probe target: 200 when dependencies answer, else 503."""
    checks: dict[str, Callable[[], Awaitable[Any]]] = {
        "database": check_database,
        "redis": check_redis,
    }
    failures: dict[str, str] = {}
    for name, check in checks.items():
        try:
            await asyncio.wait_for(check(), timeout=_CHECK_TIMEOUT_SECONDS)
        except Exception as exc:
            failures[name] = type(exc).__name__
    if failures:
        return JSONResponse(
            status_code=503, content={"status": "not-ready", "failures": failures}
        )
    return JSONResponse(status_code=200, content={"status": "ready"})


app.mount("/", sio_app)


if __name__ == "__main__":
    uvicorn.run("main:app", port=5000, host="0.0.0.0", reload=False)
