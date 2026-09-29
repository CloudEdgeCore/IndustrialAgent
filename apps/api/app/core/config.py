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
    redis_url: str = "redis://localhost:16379/0"

    minio_endpoint: str = "localhost:9000"
    minio_root_user: str = "minioadmin"
    minio_root_password: str = "minioadmin"


settings = Settings()
