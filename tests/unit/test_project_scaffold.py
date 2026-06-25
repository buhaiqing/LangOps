"""Project scaffold tests — Task 1 (pyproject, requirements, docker-compose)."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_pyproject_declares_langops_package() -> None:
    """pyproject.toml must declare langops with Python 3.11+."""
    pyproject = ROOT / "pyproject.toml"
    assert pyproject.is_file(), "pyproject.toml must exist"

    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    project = data["project"]
    assert project["name"] == "langops"
    assert project["version"] == "0.1.0"
    assert project["requires-python"] == ">=3.11"

    dep_names = {dep.split("[")[0].split(">=")[0].split("==")[0] for dep in project["dependencies"]}
    required = {"fastapi", "langfuse", "chromadb", "openai", "structlog", "tenacity"}
    assert required <= dep_names


def test_requirements_lists_core_dependencies() -> None:
    """requirements.txt must list core runtime dependencies."""
    req_file = ROOT / "requirements.txt"
    assert req_file.is_file(), "requirements.txt must exist"

    text = req_file.read_text(encoding="utf-8")
    for package in ("fastapi", "uvicorn", "pydantic", "langfuse", "chromadb", "openai"):
        assert package in text, f"{package} missing from requirements.txt"


def test_docker_compose_defines_dependency_stack() -> None:
    """docker-compose.yml must define Langfuse, Postgres, ChromaDB, Redis."""
    compose_file = ROOT / "docker-compose.yml"
    assert compose_file.is_file(), "docker-compose.yml must exist"

    import yaml

    compose = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
    services = set(compose["services"].keys())
    assert {"langfuse-server", "postgres", "chromadb", "redis"} <= services

    langfuse = compose["services"]["langfuse-server"]
    assert "3000:3000" in langfuse["ports"]
    assert compose["services"]["chromadb"]["ports"] == ["8001:8000"]


@pytest.mark.parametrize(
    "pattern",
    [".env", "venv/", ".pytest_cache/", "data/", "logs/", ".mypy_cache/"],
)
def test_gitignore_ignores_sensitive_and_generated_paths(pattern: str) -> None:
    """`.gitignore` must exclude secrets, venv, and caches."""
    gitignore = ROOT / ".gitignore"
    assert gitignore.is_file()
    content = gitignore.read_text(encoding="utf-8")
    assert pattern in content, f".gitignore must contain {pattern!r}"
