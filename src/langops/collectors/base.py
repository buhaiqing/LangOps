"""Base collector interface."""

from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Any

from langops.models import Alert


class BaseCollector(ABC):
    """Abstract base class for data collectors."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    @abstractmethod
    async def collect(
        self,
        alert: Alert,
        time_window: timedelta = timedelta(minutes=30),
    ) -> dict[str, Any]:
        """Collect data related to an alert."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the collector is healthy."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Collector name."""
