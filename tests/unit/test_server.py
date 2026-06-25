"""Server entry point tests."""

from unittest.mock import patch

from langops.server import main


def test_main_is_callable() -> None:
    assert callable(main)


@patch("langops.server.uvicorn.run")
def test_main_starts_uvicorn(mock_run) -> None:
    main()
    mock_run.assert_called_once_with(
        "langops.web:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        workers=1,
    )
