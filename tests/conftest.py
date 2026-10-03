"""测试公共设施：脚本化假 LLM + 会话级环境准备。"""

import os
import sys
from collections.abc import Callable, Iterator
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


@pytest.fixture(scope="session", autouse=True)
def _ensure_knowledge_base() -> Iterator[None]:
    """保证知识库已导入 —— 测试不应依赖其他测试文件的执行顺序。

    回归点：原先只有 ``tests/integration/test_rag_tool_db.py`` 的模块级 fixture 会
    ingest 文档，而按字母序更早的 ``test_api_db.py`` 已经断言"文档数 ≥ 6"。
    在全新数据库（例如 CI）上，该断言必然失败 —— 只是本地库里恰好已有数据而未被发现。

    数据库不可用或未迁移时静默返回，不做任何跳过/失败处理（集成测试各自会跳过）。
    """
    try:
        import psycopg
    except ImportError:  # pragma: no cover - psycopg 是运行依赖
        yield
        return

    from tools.db import normalize_database_url
    from tools.settings import settings

    url = normalize_database_url(os.environ.get("DATABASE_URL", settings.database_url))
    try:
        with psycopg.connect(url, connect_timeout=3) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM documents")
            if cur.fetchone()[0] > 0:
                yield
                return
    except Exception:  # noqa: BLE001 - 无库/未迁移时交给各集成测试自行跳过
        yield
        return

    try:
        from tools.rag.ingest import ingest_documents

        ingest_documents()
    except Exception:  # noqa: BLE001 - 导入失败不影响其余测试
        pass
    yield

