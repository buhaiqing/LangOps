"""Alert deduplication models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DedupInfo(BaseModel):
    """Alert noise reduction decision metadata.

    Returned in ``AnalysisResponse.dedup`` to explain whether the alert was
    processed or suppressed by the de-duplication layer.
    """

    action: Literal["process", "suppress"] = Field(
        ...,
        description=(
            '``"process"`` — alert passed dedup and was analyzed; '
            '``"suppress"`` — alert was skipped (duplicate within window)'
        ),
    )
    fingerprint: str = Field(
        ...,
        description="Hash-based group fingerprint derived from source + category + resource",
    )
    occurrence_count: int = Field(
        ...,
        ge=1,
        description="How many times this fingerprint appeared in the current window",
    )
    window_seconds: int = Field(
        ...,
        description="Dedup window size in seconds (configured via ALERT_DEDUP_WINDOW_SECONDS)",
    )
    message: str = Field(
        ...,
        description="Human-readable explanation of the dedup decision",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "action": "process",
                    "fingerprint": "fp-a1b2c3d4e5",
                    "occurrence_count": 1,
                    "window_seconds": 900,
                    "message": "First occurrence, proceeding with analysis",
                },
                {
                    "action": "suppress",
                    "fingerprint": "fp-a1b2c3d4e5",
                    "occurrence_count": 3,
                    "window_seconds": 900,
                    "message": "3rd occurrence within 900s window, suppressed",
                },
            ]
        }
    )
