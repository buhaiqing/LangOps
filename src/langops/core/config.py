"""Configuration management using Pydantic Settings."""

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_config(
    prefix: str,
    env_file: str = ".env",
    env_file_encoding: str = "utf-8",
) -> SettingsConfigDict:
    return SettingsConfigDict(
        env_prefix=prefix,
        env_file=env_file,
        env_file_encoding=env_file_encoding,
        extra="ignore",
    )


class LLMSettings(BaseSettings):
    """LLM configuration."""

    model_config = _env_config("LLM_")

    provider: str = Field(default="openai", description="LLM provider")
    base_url: str | None = Field(default=None, description="Custom API base URL (e.g. for Azure, proxy)")
    model: str = Field(default="gpt-4", description="Model name")
    api_key: str = Field(..., description="API key")
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=2000, ge=1)
    timeout: int = Field(default=30, ge=1)


class LangfuseSettings(BaseSettings):
    """Langfuse configuration."""

    model_config = _env_config("LANGFUSE_")

    host: str = Field(default="http://localhost:3000")
    public_key: str = Field(..., description="Public key")
    secret_key: str = Field(..., description="Secret key")
    release: str | None = Field(default=None)


class PrometheusSettings(BaseSettings):
    """Prometheus configuration."""

    model_config = _env_config("PROMETHEUS_")

    url: str = Field(default="http://localhost:9090")
    timeout: int = Field(default=10)
    scrape_interval: int = Field(default=15)


class AliyunSettings(BaseSettings):
    """Alibaba Cloud configuration."""

    model_config = _env_config("ALIYUN_")

    access_key_id: str = Field(default="", description="Access key ID")
    access_key_secret: str = Field(default="", description="Access key secret")
    region: str = Field(default="cn-hangzhou", description="Default region")
    cms_endpoint: str = Field(default="metrics.aliyuncs.com", description="CMS API endpoint")


class VectorStoreSettings(BaseSettings):
    """Vector store configuration."""

    model_config = _env_config("VECTOR_")

    type: str = Field(default="chromadb")
    host: str = Field(default="localhost")
    port: int = Field(default=8001)
    collection_name: str = Field(default="ops_knowledge")
    persist_directory: str | None = Field(default=None)


class RAGSettings(BaseSettings):
    """RAG (Retrieval Augmented Generation) enhancement configuration."""

    model_config = _env_config("RAG_")

    hyde_enabled: bool = Field(
        default=True, description="Enable HyDE query rewriting"
    )
    rerank_enabled: bool = Field(
        default=True, description="Enable cross-encoder reranking"
    )
    rerank_model: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2",
        description="Cross-encoder model for reranking",
    )
    rerank_fetch_k: int = Field(
        default=10, ge=5, le=50, description="Number of documents to fetch for reranking"
    )


class FeishuSettings(BaseSettings):
    """Feishu notification configuration."""

    model_config = _env_config("FEISHU_")

    webhook: str = Field(default="", description="Feishu bot webhook URL")


class DingtalkSettings(BaseSettings):
    """DingTalk notification configuration."""

    model_config = _env_config("DINGTALK_")

    webhook: str = Field(default="", description="DingTalk bot webhook URL")


class WechatWorkSettings(BaseSettings):
    """WeChat Work (企业微信) notification configuration."""

    model_config = _env_config("WECHAT_WORK_")

    webhook: str = Field(default="", description="WeChat Work bot webhook URL")


class AlertDedupSettings(BaseSettings):
    """Alert noise reduction configuration."""

    model_config = _env_config("ALERT_DEDUP_")

    enabled: bool = Field(default=True, description="Enable alert deduplication")
    window_seconds: int = Field(default=900, ge=60, le=86400, description="Dedup window in seconds")


class RemediationSettings(BaseSettings):
    """Remediation execution configuration."""

    model_config = _env_config("REMEDIATION_")

    enabled: bool = Field(default=True, description="Register remediation plans after analysis")
    execution_enabled: bool = Field(default=False, description="Allow real command execution")


class JiraSettings(BaseSettings):
    """JIRA integration configuration."""

    model_config = _env_config("JIRA_")

    url: str = Field(
        default="", description="JIRA base URL (e.g. https://your-domain.atlassian.net)"
    )
    username: str = Field(default="", description="JIRA username or email")
    api_token: str = Field(default="", description="JIRA API token")
    project: str = Field(default="ALERTS", description="Project key for new issues")
    enabled: bool = Field(default=False, description="Enable JIRA integration")
    timeout: int = Field(default=10, ge=1, description="HTTP timeout in seconds")


class StorageSettings(BaseSettings):
    """Storage configuration — SQLite by default, PostgreSQL optional."""

    model_config = _env_config("STORAGE_")

    url: str = Field(
        default="sqlite:///.langops/data.db",
        description="Database URL (sqlite:// or postgresql://)",
    )
    echo: bool = Field(default=False, description="Log SQL statements")


class WebhookSettings(BaseSettings):
    """Webhook receiver configuration."""

    model_config = _env_config("WEBHOOK_")

    max_payload_bytes: int = Field(default=1_048_576, ge=1024, description="Max webhook body size")
    max_alerts_per_batch: int = Field(default=100, ge=1, le=1000, description="Max alerts per callback")
    audit_log_path: str = Field(default="logs/langops-audit.log", description="Audit log file path")
    audit_log_retention_days: int = Field(default=7, ge=1, le=90, description="Audit log retention days")
    coalesce_max_buffered_alerts: int = Field(default=500, ge=10, le=10_000, description="Coalesce buffer cap")
    concurrency: int = Field(default=10, ge=1, le=100, description="Webhook processing concurrency limit")


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = Field(default="LangOps")
    app_version: str = Field(default="0.1.0")
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")

    # Server
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    workers: int = Field(default=1)

    # Sub-configs
    llm: LLMSettings = Field(default_factory=LLMSettings)  # type: ignore[arg-type]
    langfuse: LangfuseSettings = Field(default_factory=LangfuseSettings)  # type: ignore[arg-type]
    prometheus: PrometheusSettings = Field(default_factory=PrometheusSettings)
    aliyun: AliyunSettings = Field(default_factory=AliyunSettings)
    vector_store: VectorStoreSettings = Field(default_factory=VectorStoreSettings)
    rag: RAGSettings = Field(default_factory=RAGSettings)

    feishu: FeishuSettings = Field(default_factory=FeishuSettings)
    dingtalk: DingtalkSettings = Field(default_factory=DingtalkSettings)
    wechat_work: WechatWorkSettings = Field(default_factory=WechatWorkSettings)
    alert_dedup: AlertDedupSettings = Field(default_factory=AlertDedupSettings)
    remediation: RemediationSettings = Field(default_factory=RemediationSettings)
    jira: JiraSettings = Field(default_factory=JiraSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    webhook: WebhookSettings = Field(default_factory=WebhookSettings)

    @model_validator(mode="before")
    @classmethod
    def _inject_env_file_into_nested(
        cls, values: dict[str, object]
    ) -> dict[str, object]:
        """Ensure all nested settings read the .env file so prefix-based env vars are found.

        Pydantic v2 instantiates nested BaseSettings via default_factory BEFORE
        model_post_init runs, so nested models fail validation (missing env vars)
        before model_post_init can fix them. This validator runs before any
        field validation, allowing us to replace the raw dicts with properly
        instantiated submodels that have the correct _env_file.
        """
        env_file = ".env"
        env_file_encoding = "utf-8"

        nested_factories: list[type[BaseSettings]] = [
            LLMSettings,
            LangfuseSettings,
            PrometheusSettings,
            AliyunSettings,
            VectorStoreSettings,
            FeishuSettings,
            DingtalkSettings,
            WechatWorkSettings,
            AlertDedupSettings,
            RemediationSettings,
            JiraSettings,
            StorageSettings,
            WebhookSettings,
        ]

        for factory in nested_factories:
            field_name = _factory_to_field_name(factory)
            if field_name in values and isinstance(values[field_name], dict):
                # Replace raw dict (from pydantic validation) with a properly
                # instantiated submodel that has _env_file configured.
                values[field_name] = factory(
                    _env_file=env_file, _env_file_encoding=env_file_encoding
                )

        return values

    @model_validator(mode="after")
    def _raise_config_errors(self) -> "Settings":
        """Translate ValidationError into human-friendly messages pointing at .env vars."""
        missing: list[str] = []
        if not self.llm.api_key:
            missing.append("LLM_API_KEY")
        if not self.langfuse.public_key:
            missing.append("LANGFUSE_PUBLIC_KEY")
        if not self.langfuse.secret_key:
            missing.append("LANGFUSE_SECRET_KEY")

        if missing:
            lines = [
                "Missing required configuration. Add these to .env:",
                *[f"  {v}" for v in missing],
                "",
                "See .env.example for all available options.",
            ]
            raise ValueError("\n".join(lines))
        return self


def _factory_to_field_name(factory: type[BaseSettings]) -> str:
    """Convert nested settings class name to its field name in Settings."""
    mapping: dict[type[BaseSettings], str] = {
        LLMSettings: "llm",
        LangfuseSettings: "langfuse",
        PrometheusSettings: "prometheus",
        AliyunSettings: "aliyun",
        VectorStoreSettings: "vector_store",
        FeishuSettings: "feishu",
        DingtalkSettings: "dingtalk",
        WechatWorkSettings: "wechat_work",
        AlertDedupSettings: "alert_dedup",
        RemediationSettings: "remediation",
        JiraSettings: "jira",
        StorageSettings: "storage",
        WebhookSettings: "webhook",
    }
    return mapping[factory]


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
