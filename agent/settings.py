"""Agent 层配置（与 apps/api/app/core/config.py 默认值保持一致）。

默认指向 Qwen（DashScope OpenAI 兼容模式），可通过环境变量切换任意
OpenAI-compatible 端点（DeepSeek / GLM / 本地模型），模型可替换（架构红线 §4-6）。
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore", env_file=str(_ENV_FILE), env_file_encoding="utf-8"
    )

    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_api_key: str | None = None
    llm_model: str = "qwen-plus"
    llm_temperature: float = 0.1
    llm_timeout: float = 180.0

    max_tool_iterations: int = 6

    # Langfuse 可观测性（未配置时自动跳过追踪）
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"


settings = AgentSettings()
