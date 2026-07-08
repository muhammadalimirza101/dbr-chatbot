"""FastAPI app factory. Run with: uvicorn app.main:app --reload"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.extension import _rate_limit_exceeded_handler

from app.config import get_settings
from app.database import async_session_factory, engine
from app.routers import auth, health, internal, kb, webhook
from app.routers.auth import limiter
from app.services.embeddings import embedding_cache


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    async with async_session_factory() as session:
        await embedding_cache.load(session)
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="DBR Chatbot Backend",
        docs_url=None,  # no public API docs in production
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.dashboard_origin],  # exact origin only, never "*"
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(kb.router)
    app.include_router(webhook.router)
    app.include_router(internal.router)
    return app


app = create_app()
