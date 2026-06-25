"""Server entry point."""

import uvicorn

from langops.core import settings


def main() -> None:
    """Run the server."""
    uvicorn.run(
        "langops.web:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        workers=1 if settings.debug else settings.workers,
    )


if __name__ == "__main__":
    main()
