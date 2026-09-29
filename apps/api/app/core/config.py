from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置。环境变量优先，未设置时使用本地开发默认值。"""

    model_config = SettingsConfigDict(extra="ignore")

    app_name: str = "Industrial AI Agent API"
    version: str = "0.1.0"
    environment: str = "dev"

    database_url: str = (
        "postgresql+psycopg://industrial:industrial@localhost:5432/industrial_agent"
    )
    # Tool 层只读账号（架构 §15：数据库只读账号）
    tool_database_url: str = (
        "postgresql+psycopg://tool_ro:tool_ro@localhost:5432/industrial_agent"
    )
    redis_url: str = "redis://localhost:16379/0"

    minio_endpoint: str = "localhost:9000"
    minio_root_user: str = "minioadmin"
    minio_root_password: str = "minioadmin"

    # Embedding（OpenAI-compatible；未配置时使用确定性本地实现，离线可测）
    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024

    # LLM（P3 启用，OpenAI-compatible 统一接口）
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str = ""


settings = Settings()
