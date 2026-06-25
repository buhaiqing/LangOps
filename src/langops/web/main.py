"""FastAPI application."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from langops.core import configure_logging, get_logger
from langops.web.api import alerts, predict, query, remediation

logger = get_logger(__name__)
STATIC_DIR = Path(__file__).resolve().parent / "static"


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
    app.include_router(predict.router, prefix="/api/v1")
    app.include_router(remediation.router, prefix="/api/v1")

    if STATIC_DIR.is_dir():
        app.mount("/ui/static", StaticFiles(directory=STATIC_DIR), name="ui-static")

        @app.get("/ui", include_in_schema=False)
        @app.get("/ui/", include_in_schema=False)
        async def web_ui() -> FileResponse:
            """Serve Web management UI."""
            return FileResponse(STATIC_DIR / "index.html")

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
            "ui": "/ui",
        }

    return app


app = create_app()
