"""FastAPI app factory. Run with: uvicorn app.main:app --reload"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.extension import _rate_limit_exceeded_handler

from app.config import get_settings
from app.database import async_session_factory, engine
from app.routers import (
    analytics,
    auth,
    conversations,
    customers,
    health,
    internal,
    kb,
    leads,
    media,
    unanswered,
    users,
    webhook,
)
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

    @app.middleware("http")
    async def security_headers(request: Request, call_next) -> Response:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        # API serves JSON + media bytes only — lock everything else down
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'"
        )
        # no-op over plain http; enforced once served via HTTPS in production
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.dashboard_origin],  # exact origin only, never "*"
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(unanswered.router)  # before kb: /kb/unanswered vs /kb/{id}
    app.include_router(kb.router)
    app.include_router(webhook.router)
    app.include_router(internal.router)
    app.include_router(conversations.router)
    app.include_router(leads.router)
    app.include_router(customers.router)
    app.include_router(users.router)
    app.include_router(media.router)
    app.include_router(analytics.router)
    return app


app = create_app()
