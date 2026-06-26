"""Configuration management using Pydantic Settings."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """LLM configuration."""

    model_config = SettingsConfigDict(env_prefix="LLM_")

    provider: str = Field(default="openai", description="LLM provider")
    base_url: str | None = Field(default=None, description="Custom API base URL (e.g. for Azure, proxy)")
    model: str = Field(default="gpt-4", description="Model name")
    api_key: str = Field(..., description="API key")
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=2000, ge=1)
    timeout: int = Field(default=30, ge=1)


class LangfuseSettings(BaseSettings):
    """Langfuse configuration."""

    model_config = SettingsConfigDict(env_prefix="LANGFUSE_")

    host: str = Field(default="http://localhost:3000")
    public_key: str = Field(..., description="Public key")
    secret_key: str = Field(..., description="Secret key")
    release: str | None = Field(default=None)


class PrometheusSettings(BaseSettings):
    """Prometheus configuration."""

    model_config = SettingsConfigDict(env_prefix="PROMETHEUS_")

    url: str = Field(default="http://localhost:9090")
    timeout: int = Field(default=10)
    scrape_interval: int = Field(default=15)


class AliyunSettings(BaseSettings):
    """Alibaba Cloud configuration."""

    model_config = SettingsConfigDict(env_prefix="ALIYUN_")

    access_key_id: str = Field(default="", description="Access key ID")
    access_key_secret: str = Field(default="", description="Access key secret")
    region: str = Field(default="cn-hangzhou", description="Default region")
    cms_endpoint: str = Field(default="metrics.aliyuncs.com", description="CMS API endpoint")


class VectorStoreSettings(BaseSettings):
    """Vector store configuration."""

    model_config = SettingsConfigDict(env_prefix="VECTOR_")

    type: str = Field(default="chromadb")
    host: str = Field(default="localhost")
    port: int = Field(default=8001)
    collection_name: str = Field(default="ops_knowledge")
    persist_directory: str | None = Field(default=None)


class RedisSettings(BaseSettings):
    """Redis configuration."""

    model_config = SettingsConfigDict(env_prefix="REDIS_")

    url: str = Field(default="redis://localhost:6379")


class FeishuSettings(BaseSettings):
    """Feishu notification configuration."""

    model_config = SettingsConfigDict(env_prefix="FEISHU_")

    webhook: str = Field(default="", description="Feishu bot webhook URL")


class DingtalkSettings(BaseSettings):
    """DingTalk notification configuration."""

    model_config = SettingsConfigDict(env_prefix="DINGTALK_")

    webhook: str = Field(default="", description="DingTalk bot webhook URL")


class WechatWorkSettings(BaseSettings):
    """WeChat Work (企业微信) notification configuration."""

    model_config = SettingsConfigDict(env_prefix="WECHAT_WORK_")

    webhook: str = Field(default="", description="WeChat Work bot webhook URL")


class AlertDedupSettings(BaseSettings):
    """Alert noise reduction configuration."""

    model_config = SettingsConfigDict(env_prefix="ALERT_DEDUP_")

    enabled: bool = Field(default=True, description="Enable alert deduplication")
    window_seconds: int = Field(default=900, ge=60, le=86400, description="Dedup window in seconds")


class RemediationSettings(BaseSettings):
    """Remediation execution configuration."""

    model_config = SettingsConfigDict(env_prefix="REMEDIATION_")

    enabled: bool = Field(default=True, description="Register remediation plans after analysis")
    execution_enabled: bool = Field(default=False, description="Allow real command execution")


class JiraSettings(BaseSettings):
    """JIRA integration configuration."""

    model_config = SettingsConfigDict(env_prefix="JIRA_")

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

    model_config = SettingsConfigDict(env_prefix="STORAGE_")

    url: str = Field(
        default="sqlite:///.langops/data.db",
        description="Database URL (sqlite:// or postgresql://)",
    )
    echo: bool = Field(default=False, description="Log SQL statements")


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
    redis: RedisSettings = Field(default_factory=RedisSettings)
    feishu: FeishuSettings = Field(default_factory=FeishuSettings)
    dingtalk: DingtalkSettings = Field(default_factory=DingtalkSettings)
    wechat_work: WechatWorkSettings = Field(default_factory=WechatWorkSettings)
    alert_dedup: AlertDedupSettings = Field(default_factory=AlertDedupSettings)
    remediation: RemediationSettings = Field(default_factory=RemediationSettings)
    jira: JiraSettings = Field(default_factory=JiraSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
