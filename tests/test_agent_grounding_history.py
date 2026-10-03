"""Grounding 校验 / 多轮会话历史 / 降级标记 测试（无需数据库，使用捕获式假 LLM）。"""

import json

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from agent.grounding import verify_grounding
from agent.history import format_history
from agent.professional import make_professional_node
from agent.report.agent import merge_report_inputs
from agent.router.agent import make_node as make_router_node
from agent.runner import _aggregate_grounding
from tools.loader import load_all_tools


class CapturingModel(BaseChatModel):
    """记录收到的提示词，并返回固定回复。"""

    reply: str = ""
    seen: list = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "capturing"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.seen.append(messages)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.reply))])

    def bind_tools(self, tools, **kwargs):  # type: ignore[override]
        return self


HISTORY = [
    {"role": "user", "content": "EQ-003 温度怎么样？"},
    {"role": "assistant", "content": "EQ-003 温度峰值 92.1℃，冷却液流量降至 14.9 L/min。"},
]


def _prompt_text(model: CapturingModel) -> str:
    return " ".join(str(message.content) for message in model.seen[0])


# ---------------------------------------------------------------- 会话历史


def test_format_history_renders_roles() -> None:
    text = format_history(HISTORY)
    assert "历史对话" in text
    assert "用户：EQ-003 温度怎么样？" in text
    assert "助手：EQ-003 温度峰值 92.1℃" in text


def test_format_history_handles_empty() -> None:
    assert format_history(None) == ""
    assert format_history([]) == ""
    assert format_history([{"role": "user", "content": "   "}]) == ""


def test_format_history_limits_and_truncates() -> None:
    long_history = [
        {"role": "user", "content": f"第{i}轮" + "x" * 600} for i in range(10)
    ]
    text = format_history(long_history)
    assert text.count("用户：") == 6, "只保留最近 6 条"
    assert "第0轮" not in text
    assert "…" in text, "超长单条需要截断"


def test_router_prompt_includes_history() -> None:
    model = CapturingModel(
        reply=json.dumps(
            {
                "task_type": "equipment_diagnosis",
                "agents": ["equipment"],
                "need_report": False,
                "reason": "追问",
            }
        )
    )
    make_router_node(model)(
        {"user_query": "那 EQ-024 呢？", "history": HISTORY, "context": {}}
    )
    text = _prompt_text(model)
    assert "历史对话" in text
    assert "EQ-003 温度峰值 92.1℃" in text
    assert "那 EQ-024 呢？" in text


def test_professional_prompt_includes_history() -> None:
    load_all_tools()
    model = CapturingModel(reply="不是 JSON")
    node = make_professional_node("equipment", "SYSTEM", model)
    node({"user_query": "那 EQ-024 呢？", "history": HISTORY, "context": {}})
    text = _prompt_text(model)
    assert "历史对话" in text
    assert "14.9 L/min" in text


# ---------------------------------------------------------------- 降级标记


def test_parse_failure_is_marked_degraded() -> None:
    load_all_tools()
    model = CapturingModel(reply="模型输出了非 JSON 内容")
    node = make_professional_node("equipment", "SYSTEM", model)
    out = node({"user_query": "EQ-003 温度", "context": {}})
    result = out["agent_results"][0]
    assert result["degraded"] is True
    assert "解析失败" in result["degraded_reason"]
    assert result["grounding"]["checked"] == 0


def test_degraded_agent_surfaces_in_report_findings() -> None:
    state = {
        "user_query": "EQ-003 温度异常",
        "agent_results": [
            {
                "agent": "equipment",
                "conclusion": {"summary": "结论解析失败", "risk_level": "medium"},
                "degraded": True,
                "degraded_reason": "结论解析失败，已保留工具执行过程供人工复核",
                "grounding": {"checked": 0, "matched": 0, "unmatched": []},
            }
        ],
        "evidence": [],
        "tool_results": [],
    }
    merged = merge_report_inputs(state)
    assert any("未通过结构化解析" in finding for finding in merged["findings"])
    assert "equipment" in merged["findings"][0]


# ---------------------------------------------------------------- Grounding


def test_grounding_matches_payload_numbers() -> None:
    conclusion = {
        "summary": "温度峰值 92.17℃，冷却液流量 14.9 L/min",
        "findings": ["连续 24 分钟超过 85℃"],
    }
    payloads = [{"max_value": 92.17, "points": 1440}, {"last_value": 14.9, "threshold": 85}]
    report = verify_grounding(conclusion, payloads)
    assert report.checked == 3, "『24 分钟』是时长，不应计入测量值校验"
    assert report.matched == report.checked
    assert report.ratio == 1.0
    assert report.is_reliable


def test_grounding_flags_hallucinated_number() -> None:
    conclusion = {"summary": "温度峰值 137.4℃，压力 88.8 bar", "findings": ["振动 9.9 mm/s"]}
    payloads = [{"max_value": 92.17}]
    report = verify_grounding(conclusion, payloads)
    assert set(report.unmatched) == {"137.4", "88.8", "9.9"}
    assert report.ratio == 0.0
    assert not report.is_reliable, "样本充足且全部未溯源时必须判为不可靠"


def test_grounding_duration_units_are_not_measurements() -> None:
    report = verify_grounding(
        {"summary": "最近 3 天连续 24 分钟、30 小时、1 号产线"}, [{"note": "none"}]
    )
    assert report.checked == 0


def test_grounding_tolerates_rounding() -> None:
    report = verify_grounding({"summary": "温度 92.2℃"}, [{"max_value": 92.17}])
    assert report.checked == 1
    assert report.matched == 1, "结论四舍五入不应判为未溯源"


def test_grounding_ignores_context_numbers_from_query() -> None:
    report = verify_grounding(
        {"summary": "连续 24 分钟超过 85℃"},
        [{"note": "no numbers"}],
        user_query="温度连续 24 分钟超过 85℃",
    )
    assert report.checked == 0, "用户问题里给出的数值属于上下文，不应计入校验"


def test_grounding_ignores_small_window_integers() -> None:
    report = verify_grounding({"summary": "最近 3 天的 7 条记录"}, [{"note": "none"}])
    assert report.checked == 0, "窗口/条数类小整数不应计入校验"


def test_grounding_does_not_alarm_on_small_samples() -> None:
    report = verify_grounding({"summary": "温度 137.4℃"}, [{"max_value": 92.17}])
    assert report.checked == 1
    assert report.is_reliable, "样本过少时不应报警"


def test_grounding_accepts_string_payloads() -> None:
    report = verify_grounding(
        {"summary": "峰值 92.17"},
        ['{"max_value": 92.17}'],
    )
    assert report.matched == 1


def test_aggregate_grounding_sums_and_lists_degraded() -> None:
    aggregate = _aggregate_grounding(
        [
            {
                "agent": "equipment",
                "grounding": {"checked": 4, "matched": 3, "unmatched": ["137.4"]},
                "degraded": False,
            },
            {
                "agent": "quality",
                "grounding": {"checked": 2, "matched": 2, "unmatched": []},
                "degraded": True,
            },
        ]
    )
    assert aggregate["checked"] == 6
    assert aggregate["matched"] == 5
    assert aggregate["unmatched"] == ["137.4"]
    assert aggregate["degraded_agents"] == ["quality"]
    assert 0.82 < aggregate["ratio"] < 0.84


def test_aggregate_grounding_without_reports() -> None:
    aggregate = _aggregate_grounding([])
    assert aggregate["checked"] == 0
    assert aggregate["ratio"] == 1.0
    assert aggregate["degraded_agents"] == []


@pytest.mark.parametrize(
    "text,expected_unmatched",
    [
        ("峰值 -12.5", ["-12.5"]),
        ("无任何数值", []),
    ],
)
def test_grounding_edge_inputs(text: str, expected_unmatched: list[str]) -> None:
    report = verify_grounding({"summary": text}, [{"note": "none"}])
    assert report.unmatched == expected_unmatched
