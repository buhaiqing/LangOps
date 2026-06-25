"""Custom exceptions for LangOps."""


class LangOpsException(Exception):
    """Base exception for LangOps."""


class ConfigurationError(LangOpsException):
    """Configuration error."""


class CollectorError(LangOpsException):
    """Data collector error."""

    def __init__(self, message: str, source: str | None = None) -> None:
        super().__init__(message)
        self.source = source


class LLMError(LangOpsException):
    """LLM service error."""

    def __init__(self, message: str, model: str | None = None) -> None:
        super().__init__(message)
        self.model = model


class VectorStoreError(LangOpsException):
    """Vector store error."""


class AnalysisError(LangOpsException):
    """Analysis processing error."""
