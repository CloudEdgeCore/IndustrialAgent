"""LLM 工厂测试：模型可替换（base_url / model 切换）与缺 Key 保护。"""

import pytest
from langchain_openai import ChatOpenAI

from agent.llm import get_chat_model
from agent.settings import settings


def test_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_api_key", None)
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        get_chat_model()


def test_factory_uses_configured_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    model = get_chat_model()
    assert isinstance(model, ChatOpenAI)
    assert model.model_name == settings.llm_model
    assert str(model.openai_api_base).startswith(settings.llm_base_url)


def test_factory_allows_model_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    model = get_chat_model(model="qwen-max")
    assert model.model_name == "qwen-max"
