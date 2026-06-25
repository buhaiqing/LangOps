"""Natural language query models."""

from typing import Any

from pydantic import BaseModel, Field


class NLQueryRequest(BaseModel):
    """Natural language query request."""

    query: str = Field(..., min_length=1, description="Natural language question")


class NLQueryResult(BaseModel):
    """Natural language query result."""

    answer: str = Field(..., description="Human-readable answer")
    promql: str | None = Field(default=None, description="Generated PromQL")
    explanation: str | None = Field(default=None, description="Query explanation")
    time_range: str = Field(default="1h", description="Suggested time range")
    data: list[dict[str, Any]] = Field(default_factory=list, description="Raw query data")


class NLQueryResponse(BaseModel):
    """API response for natural language query."""

    success: bool = Field(..., description="Whether query succeeded")
    data: NLQueryResult | None = Field(default=None, description="Query result")
    error: str | None = Field(default=None, description="Error message if failed")
