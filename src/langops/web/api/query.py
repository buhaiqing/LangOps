"""Natural language query API routes."""

from fastapi import APIRouter, Depends, status

from langops.agent.nl_query_engine import NLQueryEngine
from langops.core.exceptions import LLMError
from langops.models import NLQueryRequest, NLQueryResponse
from langops.web.dependencies import get_nl_query_engine

router = APIRouter(prefix="/query", tags=["query"])


@router.post(
    "",
    response_model=NLQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Natural language query",
    description="Convert natural language to PromQL, execute against Prometheus, and return an answer.",
)
async def natural_language_query(
    request: NLQueryRequest,
    engine: NLQueryEngine = Depends(get_nl_query_engine),
) -> NLQueryResponse:
    """Process a natural language metrics query."""
    try:
        result = await engine.process(request.query)
        return NLQueryResponse(success=True, data=result, error=None)
    except LLMError as exc:
        return NLQueryResponse(success=False, data=None, error=str(exc))
    except Exception as exc:
        return NLQueryResponse(success=False, data=None, error=str(exc))
