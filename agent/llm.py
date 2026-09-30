"""LLM 工厂：OpenAI-compatible 统一接口（架构红线 §4-6：LLM 层必须可替换）。

Qwen（DashScope 兼容模式）/ DeepSeek / GLM / 本地模型均通过 base_url + model 切换，
不硬编码任何单一厂商 SDK。
"""

from langchain_openai import ChatOpenAI

from agent.settings import settings


def get_chat_model(**overrides: object) -> ChatOpenAI:
    if not settings.llm_api_key:
        raise RuntimeError(
            "未配置 LLM_API_KEY：请在 .env 中填写（Qwen DashScope Key），"
            "或注入其他 OpenAI-compatible 配置（LLM_BASE_URL / LLM_MODEL）"
        )
    return ChatOpenAI(
        model=overrides.pop("model", settings.llm_model),
        base_url=overrides.pop("base_url", settings.llm_base_url),
        api_key=settings.llm_api_key,
        temperature=overrides.pop("temperature", settings.llm_temperature),
        timeout=overrides.pop("timeout", settings.llm_timeout),
        max_retries=2,
        **overrides,
    )
