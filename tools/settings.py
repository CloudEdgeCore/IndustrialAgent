"""Tool 层配置（与 apps/api/app/core/config.py 默认值保持一致）。

Tool 层独立于 API 层可运行（如 python -m tools.rag），因此单独读取环境变量。
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class ToolSettings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore", env_file=str(_ENV_FILE), env_file_encoding="utf-8"
    )

    # 相对时间窗口锚点：
    #   data（默认）= 锚定数据最新时间，模拟/回放数据集下窗口始终命中数据
    #   now         = 锚定真实时钟，生产接入实时数据流时使用（配合滞后告警）
    window_anchor: str = "data"

    database_url: str = (
        "postgresql+psycopg://industrial:industrial@localhost:5432/industrial_agent"
    )
    tool_database_url: str = (
        "postgresql+psycopg://tool_ro:tool_ro@localhost:5432/industrial_agent"
    )

    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024


settings = ToolSettings()
