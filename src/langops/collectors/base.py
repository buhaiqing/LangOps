"""Base collector interface."""

from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from langops.core import get_logger
from langops.models import Alert

logger = get_logger(__name__)

# Circuit breaker defaults: 3 retries, 1s → 4s exponential backoff,
# fail-fast after exhaustion.
COLLECTOR_RETRY = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    reraise=True,
)


class BaseCollector(ABC):
    """Abstract base class for data collectors."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._circuit_open_until: float = 0.0
        self._consecutive_failures: int = 0
        self._circuit_failure_threshold: int = 5
        self._circuit_open_seconds: float = 60.0

    async def collect(
        self,
        alert: Alert,
        time_window: timedelta = timedelta(minutes=30),
    ) -> dict[str, Any]:
        """Collect data related to an alert with circuit breaker protection."""
        import time

        if time.time() < self._circuit_open_until:
            logger.warning(
                "Circuit breaker OPEN — skipping collect",
                collector=self.name,
                alert_id=alert.id,
            )
            return {"error": "circuit breaker open"}

        try:
            result = await self._do_collect(alert, time_window)
            self._consecutive_failures = 0
            return result
        except Exception:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._circuit_failure_threshold:
                self._circuit_open_until = time.time() + self._circuit_open_seconds
                logger.warning(
                    "Circuit breaker TRIPPED — opening for %.0fs",
                    self._circuit_open_seconds,
                    collector=self.name,
                    consecutive_failures=self._consecutive_failures,
                )
            raise

    @abstractmethod
    async def _do_collect(
        self,
        alert: Alert,
        time_window: timedelta = timedelta(minutes=30),
    ) -> dict[str, Any]:
        """Actual collection logic — subclasses implement this instead of collect()."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the collector is healthy."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Collector name."""

    async def close(self) -> None:
        """Release resources. Override in subclasses that hold sessions."""
