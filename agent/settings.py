"""Agent 层配置（与 apps/api/app/core/config.py 默认值保持一致）。

默认指向 Qwen（DashScope OpenAI 兼容模式），可通过环境变量切换任意
OpenAI-compatible 端点（DeepSeek / GLM / 本地模型），模型可替换（架构红线 §4-6）。
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_api_key: str | None = None
    llm_model: str = "qwen-plus"
    llm_temperature: float = 0.1
    llm_timeout: float = 60.0

    max_tool_iterations: int = 6


settings = AgentSettings()
