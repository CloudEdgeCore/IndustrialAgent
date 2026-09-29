"""测试公共设施：脚本化假 LLM（按顺序返回预设消息，用于离线/确定性测试）。"""

import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

sys.path.insert(0, str(Path(__file__).parent))


class ScriptedChatModel(BaseChatModel):
    responses: list[AIMessage] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        if not self.responses:
            raise AssertionError("ScriptedChatModel 脚本已耗尽")
        message = self.responses.pop(0)
        return ChatResult(generations=[ChatGeneration(message=message)])

    def bind_tools(self, tools, **kwargs):  # type: ignore[override]
        return self


@pytest.fixture
def scripted_llm() -> Callable[[list[AIMessage]], ScriptedChatModel]:
    def factory(responses: list[AIMessage]) -> ScriptedChatModel:
        return ScriptedChatModel(responses=list(responses))

    return factory
