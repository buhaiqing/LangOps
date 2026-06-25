"""FastAPI application."""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from langops.core import configure_logging, get_logger
from langops.web.api import alerts, query

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    configure_logging()
    logger.info("LangOps starting up", version="0.1.0")
    yield
    logger.info("LangOps shutting down")


def create_app() -> FastAPI:
    """Create FastAPI application."""
    app = FastAPI(
        title="LangOps",
        description="AI-powered intelligent operations platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(alerts.router, prefix="/api/v1")
    app.include_router(query.router, prefix="/api/v1")

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "healthy", "version": "0.1.0"}

    @app.get("/")
    async def root() -> dict[str, Any]:
        """Root endpoint."""
        return {
            "name": "LangOps",
            "version": "0.1.0",
            "description": "AI-powered intelligent operations platform",
            "docs": "/docs",
        }

    return app


app = create_app()
