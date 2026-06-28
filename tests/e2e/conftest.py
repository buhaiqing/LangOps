"""E2E test configuration — starts a real LangOps server.

The server runs with:
  - SQLite storage (no Postgres)
  - Local ChromaDB (PersistentClient, no Docker)
  - Prometheus / Langfuse mocked or unreachable (tests tolerate this)
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path

import pytest
import requests

# ── project root & venv paths ──────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"
E2E_PORT = 18100  # high port to avoid conflicts
BASE_URL = f"http://127.0.0.1:{E2E_PORT}"


def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


@pytest.fixture(scope="session", autouse=True)
def _ensure_port_free():
    if not _port_is_free(E2E_PORT):
        pytest.skip(f"Port {E2E_PORT} is already in use — stop the other process first.")


@pytest.fixture(scope="session")
def server_url() -> str:
    """Start the LangOps server, yield the base URL, then shut it down."""
    # ── environment for the child process ──────────────────────────────
    env = os.environ.copy()
    env.update({
        "PORT": str(E2E_PORT),
        "LLM_API_KEY": os.getenv("LLM_API_KEY", "sk-test-placeholder"),
        "LLM_BASE_URL": os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "LLM_MODEL": os.getenv("LLM_MODEL", "qwen-plus"),
        "LANGFUSE_PUBLIC_KEY": os.getenv("LANGFUSE_PUBLIC_KEY", "pk-test"),
        "LANGFUSE_SECRET_KEY": os.getenv("LANGFUSE_SECRET_KEY", "sk-lf-test"),
        "LANGFUSE_HOST": os.getenv("LANGFUSE_HOST", "http://localhost:3000"),
        "LANGFUSE_TRACING_ENABLED": "false",  # disable Langfuse OTLP retries for E2E
        "PROMETHEUS_URL": "",  # disable Prometheus (not needed for E2E)
        "VECTOR_PERSIST_DIRECTORY": str(PROJECT_ROOT / ".langops" / "e2e_chroma"),
        "STORAGE_URL": f"sqlite:///{PROJECT_ROOT / '.langops' / 'e2e.db'}",
        "DEBUG": "false",
        "LOG_LEVEL": "INFO",
    })

    # ensure data dir exists
    (PROJECT_ROOT / ".langops").mkdir(parents=True, exist_ok=True)

    proc = subprocess.Popen(
        [str(VENV_PYTHON), "-m", "langops.server"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(PROJECT_ROOT),
    )

    # ── wait until the server is healthy ───────────────────────────────
    deadline = time.time() + 30
    last_err = ""
    while time.time() < deadline:
        try:
            r = requests.get(f"{BASE_URL}/health", timeout=2)
            if r.status_code == 200:
                break
        except requests.ConnectionError as e:
            last_err = str(e)
        time.sleep(0.5)
    else:
        stdout = ""
        try:
            proc.terminate()
            proc.wait(timeout=5)
            stdout = (proc.stdout.read() or b"").decode()
        except Exception:
            pass
        pytest.skip(
            f"Server did not start within 30 s on port {E2E_PORT}.\n"
            f"Last error: {last_err}\nServer stdout:\n{stdout}"
        )

    yield BASE_URL

    # ── shutdown ───────────────────────────────────────────────────────
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
