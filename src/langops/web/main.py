"""FastAPI application."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import generate_latest

from langops.core import configure_logging, get_logger
from langops.storage import close_storage, get_storage
from langops.web.api import alerts, predict, query, remediation
from langops.web.dependencies import close_notification_service
from langops.web.metrics import PROMETHEUS_CONTENT_TYPE
from langops.web.middleware import RequestIDMiddleware

logger = get_logger(__name__)
STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info("LangOps starting up", version="0.1.0")
    await get_storage()
    yield
    await close_notification_service()
    await close_storage()
    logger.info("LangOps shutting down")


def create_app() -> FastAPI:
    """Create FastAPI application."""
    app = FastAPI(
        title="LangOps",
        description="AI-powered intelligent operations platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Request tracing middleware — must be added first (outermost)
    app.add_middleware(RequestIDMiddleware)

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

    @app.get("/metrics")
    async def metrics() -> Response:
        """Prometheus metrics endpoint."""
        return PlainTextResponse(
            content=generate_latest(),
            media_type=PROMETHEUS_CONTENT_TYPE,
        )

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
