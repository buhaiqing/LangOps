"""pytest configuration and fixtures."""

import os

# Required before langops.core imports (Settings validates nested secrets at load time).
os.environ.setdefault("LLM_API_KEY", "sk-test")
os.environ.setdefault("LANGFUSE_PUBLIC_KEY", "pk-test")
os.environ.setdefault("LANGFUSE_SECRET_KEY", "sk-lf-test")
