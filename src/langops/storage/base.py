"""Abstract repository interfaces for LangOps storage layer.

All repositories follow the Repository pattern — concrete implementations
can be swapped without changing calling code.
"""

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from langops.models import Alert, AnalysisResult, RemediationPlan


class AlertRepository(ABC):
    """Persist alert data and analysis results."""

    @abstractmethod
    async def save(self, alert: "Alert") -> None:
        """Store a raw alert record."""
        ...

    @abstractmethod
    async def get(self, alert_id: str) -> dict | None:
        """Retrieve an alert by ID."""
        ...

    @abstractmethod
    async def list_recent(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """Return alerts in reverse-chronological order."""
        ...

    @abstractmethod
    async def count(self) -> int:
        """Total number of stored alerts."""
        ...


class AnalysisRepository(ABC):
    """Persist LLM analysis results."""

    @abstractmethod
    async def save(self, result: "AnalysisResult") -> None:
        """Store an analysis result."""
        ...

    @abstractmethod
    async def get_by_alert(self, alert_id: str) -> dict | None:
        """Get analysis result for a specific alert."""
        ...

    @abstractmethod
    async def list_recent(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """Return analyses in reverse-chronological order."""
        ...


class DedupRepository(ABC):
    """Persist alert deduplication state."""

    @abstractmethod
    async def get(self, fingerprint: str) -> dict | None:
        """Get dedup record by fingerprint."""
        ...

    @abstractmethod
    async def upsert(
        self, fingerprint: str, first_seen: datetime, last_seen: datetime, count: int
    ) -> None:
        """Create or update a dedup record."""
        ...

    @abstractmethod
    async def purge_expired(self, cutoff: datetime) -> int:
        """Delete records older than cutoff. Return count deleted."""
        ...

    @abstractmethod
    async def count(self) -> int:
        """Number of active dedup records."""
        ...


class RemediationRepository(ABC):
    """Persist remediation plans."""

    @abstractmethod
    async def save(self, plan: "RemediationPlan") -> None:
        """Store a remediation plan."""
        ...

    @abstractmethod
    async def get(self, plan_id: str) -> dict | None:
        """Get a remediation plan by ID."""
        ...

    @abstractmethod
    async def update_status(
        self,
        plan_id: str,
        status: str,
        approved_by: str | None = None,
        execution_output: str | None = None,
        jira_issue_key: str | None = None,
    ) -> None:
        """Update plan status and related fields."""
        ...

    @abstractmethod
    async def list_pending(self) -> list[dict]:
        """Return all plans in PENDING_APPROVAL status."""
        ...

    @abstractmethod
    async def list_recent(self, limit: int = 50) -> list[dict]:
        """Return plans in reverse-chronological order."""
        ...


class Storage(ABC):
    """Unified storage facade — provides access to all repositories."""

    @abstractmethod
    async def initialize(self) -> None:
        """Create tables / run migrations."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Release resources."""
        ...

    @property
    @abstractmethod
    def alerts(self) -> AlertRepository: ...

    @property
    @abstractmethod
    def analyses(self) -> AnalysisRepository: ...

    @property
    @abstractmethod
    def dedup(self) -> DedupRepository: ...

    @property
    @abstractmethod
    def remediations(self) -> RemediationRepository: ...
