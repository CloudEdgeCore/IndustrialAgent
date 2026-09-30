"""LLM 工厂：OpenAI-compatible 统一接口（架构红线 §4-6：LLM 层必须可替换）。

Qwen（DashScope 兼容模式）/ DeepSeek / GLM / 本地模型均通过 base_url + model 切换，
不硬编码任何单一厂商 SDK。

可观测性（P6）：配置 LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY 后自动附加
Langfuse 回调（LLM 调用链、Prompt、Token、延迟全链路追踪）；未配置时零开销跳过。
"""

import logging
import os

from langchain_openai import ChatOpenAI

from agent.settings import settings

logger = logging.getLogger("agent.llm")


def _langfuse_callbacks() -> list:
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return []
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
    os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
    os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)
    try:
        from langfuse.langchain import CallbackHandler

        return [CallbackHandler()]
    except Exception as exc:  # noqa: BLE001 - 追踪失败不影响主流程
        logger.warning("Langfuse 回调初始化失败，已跳过追踪: %s", exc)
        return []


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
        callbacks=overrides.pop("callbacks", _langfuse_callbacks()),
        **overrides,
    )
