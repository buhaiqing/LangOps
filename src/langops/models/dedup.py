"""Alert deduplication models."""

from typing import Literal

from pydantic import BaseModel, Field


class DedupInfo(BaseModel):
    """Alert noise reduction decision metadata."""

    action: Literal["process", "suppress"] = Field(
        ..., description="Whether alert was processed or suppressed"
    )
    fingerprint: str = Field(..., description="Alert group fingerprint")
    occurrence_count: int = Field(..., ge=1, description="Occurrences in current window")
    window_seconds: int = Field(..., description="Dedup window size in seconds")
    message: str = Field(..., description="Human-readable dedup explanation")
