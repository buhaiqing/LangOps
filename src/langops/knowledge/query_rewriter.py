"""HyDE Query Rewriter - Expands short queries into hypothetical documents."""

from typing import Any

from langops.core import get_logger

logger = get_logger(__name__)


class QueryRewriter:
    """
    Hypothetical Document Embedding (HyDE) query rewriter.

    Transforms short user queries into hypothetical failure case documents
    to bridge the semantic gap between query and knowledge base documents.
    """

    def __init__(
        self,
        llm_client: Any,
        model: str = "gpt-4",
        temperature: float = 0.3,
        max_tokens: int = 500,
    ):
        """
        Initialize the query rewriter.

        Args:
            llm_client: OpenAI-compatible LLM client
            model: Model name to use for rewriting
            temperature: Sampling temperature (lower = more deterministic)
            max_tokens: Maximum tokens for rewritten document
        """
        self.llm_client = llm_client
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def rewrite(self, query: str, alert_context: dict[str, Any] | None = None) -> str:
        """
        Rewrite a query into a hypothetical failure case document.

        Args:
            query: Original user query (e.g., "order-service CPU high")
            alert_context: Additional alert context (service, namespace, severity, etc.)

        Returns:
            Hypothetical document describing the failure case
            Falls back to original query if LLM call fails
        """
        alert_context = alert_context or {}

        try:
            prompt = self._build_prompt(query, alert_context)

            response = await self.llm_client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert in IT operations. Given a short query about a "
                            "system issue, expand it into a detailed hypothetical failure case "
                            "document that would appear in an operations knowledge base. "
                            "Include: fault title, description, root cause analysis, and solution. "
                            "Be specific and technical. Write in Chinese if the query is in "
                            "Chinese."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            rewritten: str = response.choices[0].message.content.strip()

            logger.info(
                "Query rewritten with HyDE",
                original_query=query[:50],
                rewritten_length=len(rewritten),
                model=self.model,
            )

            return rewritten

        except Exception as exc:
            logger.warning(
                "HyDE query rewriting failed, falling back to original",
                query=query[:50],
                error=str(exc),
            )
            return query

    def _build_prompt(self, query: str, alert_context: dict[str, Any]) -> str:
        """Build the prompt for query rewriting."""
        context_str = ""
        if alert_context:
            context_parts = []
            if "service" in alert_context:
                context_parts.append(f"服务: {alert_context['service']}")
            if "namespace" in alert_context:
                context_parts.append(f"命名空间: {alert_context['namespace']}")
            if "severity" in alert_context:
                context_parts.append(f"严重程度: {alert_context['severity']}")
            if context_parts:
                context_str = "\n".join(context_parts)

        prompt = f"""请将以下运维查询扩展为一个详细的假设故障案例文档：

用户查询: {query}
{context_str and f'\\n上下文信息:\\n{context_str}' or ''}

请生成一个详细的故障案例文档，包含以下部分：
- 故障标题
- 故障描述
- 根因分析
- 解决方案

文档应该足够详细，以便与知识库中的真实案例进行语义匹配。"""

        return prompt
