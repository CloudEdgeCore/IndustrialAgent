"""Report Tool 测试：字段齐全性强制（Evidence-based）+ 渲染 + 落库。"""

import os
from datetime import UTC, datetime

import psycopg
import pytest

from tools.base import PermissionDeniedError, ToolContext, ToolValidationError
from tools.db import normalize_database_url
from tools.executor import execute_tool
from tools.registry import default_registry
from tools.reports import tool as _tool  # noqa: F401  触发注册
from tools.reports.models import ReportRequest
from tools.reports.tool import render_markdown
from tools.settings import settings

REPORT_CTX = ToolContext(agent="report")

VALID_REPORT = {
    "report_type": "equipment_diagnosis",
    "title": "EQ-003 主轴温度异常诊断报告",
    "problem": "3 号设备主轴温度连续 20 分钟超过 85℃，伴随 E102 报警。",
    "data_range": "EQ-003 近 2 小时温度/流量时序 + 近 60 天报警与维修记录",
    "findings": ["主轴温度末段达 91℃", "冷却液流量下降约 18%"],
    "root_causes": [
        {
            "cause": "冷却系统效率下降（过滤器堵塞）",
            "confidence": "high",
            "evidence": ["冷却液流量从 17.8 L/min 降至 15.1 L/min", "E102 报警为活跃状态"],
        }
    ],
    "recommendations": ["检查冷却液液位", "检查冷却泵", "更换过滤器"],
    "risk_level": "high",
    "sources": ["postgres:sensor_readings", "postgres:alarms", "knowledge:E102 SOP"],
    "equipment_id": "EQ-003",
}


def test_registered() -> None:
    assert "report.generate" in default_registry.names()


def test_render_markdown_contains_all_sections() -> None:
    request = ReportRequest(**VALID_REPORT)
    markdown = render_markdown(request, datetime(2026, 9, 29, 12, 0, tzinfo=UTC))
    for section in (
        "一、问题概述",
        "二、数据范围",
        "三、异常发现",
        "四、根因候选",
        "五、建议排查顺序",
        "六、风险提示",
        "七、数据来源",
    ):
        assert section in markdown
    assert "置信度：高" in markdown
    assert "风险等级：高" in markdown
    assert "1. 检查冷却液液位" in markdown


def test_evidence_based_fields_are_mandatory() -> None:
    with pytest.raises(ToolValidationError):
        execute_tool(
            "report.generate",
            {**VALID_REPORT, "findings": []},
            REPORT_CTX,
        )
    with pytest.raises(ToolValidationError):
        execute_tool(
            "report.generate",
            {**VALID_REPORT, "sources": []},
            REPORT_CTX,
        )
    with pytest.raises(ToolValidationError):
        execute_tool(
            "report.generate",
            {
                **VALID_REPORT,
                "root_causes": [{"cause": "x", "confidence": "high", "evidence": []}],
            },
            REPORT_CTX,
        )
    with pytest.raises(ToolValidationError):
        execute_tool(
            "report.generate",
            {**VALID_REPORT, "risk_level": "extreme"},
            REPORT_CTX,
        )


def test_bad_equipment_id_rejected() -> None:
    with pytest.raises(ToolValidationError, match="非法设备编号"):
        execute_tool(
            "report.generate",
            {**VALID_REPORT, "equipment_id": "EQ-3; DROP"},
            REPORT_CTX,
        )


def test_permission_matrix() -> None:
    with pytest.raises(PermissionDeniedError):
        execute_tool("report.generate", VALID_REPORT, ToolContext(agent="equipment"))
    with pytest.raises(PermissionDeniedError):
        execute_tool("report.generate", VALID_REPORT, ToolContext(agent="router"))


@pytest.mark.integration
def test_generate_report_persists() -> None:
    url = normalize_database_url(os.environ.get("DATABASE_URL", settings.database_url))
    try:
        conn = psycopg.connect(url, connect_timeout=5)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL 不可用，跳过集成测试")

    result = execute_tool("report.generate", VALID_REPORT, REPORT_CTX)
    report_id = result.data["report_id"]
    assert report_id >= 1
    assert result.meta["source"] == "postgres:reports"

    with conn.cursor() as cur:
        cur.execute(
            "SELECT title, risk_level, status, created_by, content_markdown "
            "FROM reports WHERE report_id = %s",
            (report_id,),
        )
        row = cur.fetchone()
    conn.close()

    assert row is not None
    assert row[0] == VALID_REPORT["title"]
    assert row[1] == "high"
    assert row[2] == "draft"
    assert row[3] == "AI"
    assert "冷却液流量下降约 18%" in row[4]
