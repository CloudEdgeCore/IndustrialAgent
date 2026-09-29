"""Report Tool：渲染结构化报告并落库（reports 表，status=draft）。"""

import json
import re
from datetime import UTC, datetime

from tools.base import ToolContext, ToolResult, ToolValidationError
from tools.db import app_db_connection
from tools.registry import default_registry
from tools.reports.models import ReportRequest

_EQUIPMENT_RE = re.compile(r"^EQ-\d{3}$")

_CONFIDENCE_LABEL = {"high": "高", "medium": "中", "low": "低"}
_RISK_LABEL = {
    "low": "低",
    "medium": "中",
    "high": "高",
    "critical": "严重",
}


def render_markdown(request: ReportRequest, generated_at: datetime) -> str:
    lines: list[str] = [f"# {request.title}", ""]
    lines.append(f"- 生成时间：{generated_at.strftime('%Y-%m-%d %H:%M UTC')}")
    if request.equipment_id:
        lines.append(f"- 设备编号：{request.equipment_id}")
    lines.append("")

    lines.append("## 一、问题概述")
    lines.append(request.problem)
    lines.append("")

    lines.append("## 二、数据范围")
    lines.append(request.data_range)
    lines.append("")

    lines.append("## 三、异常发现")
    lines.extend(f"- {item}" for item in request.findings)
    lines.append("")

    lines.append("## 四、根因候选")
    if request.root_causes:
        for index, candidate in enumerate(request.root_causes, start=1):
            lines.append(
                f"### 根因 {index}：{candidate.cause}"
                f"（置信度：{_CONFIDENCE_LABEL[candidate.confidence]}）"
            )
            lines.append("证据：")
            lines.extend(f"- {evidence}" for evidence in candidate.evidence)
            lines.append("")
    else:
        lines.append("（待进一步分析）")
        lines.append("")

    lines.append("## 五、建议排查顺序")
    lines.extend(
        f"{index}. {step}" for index, step in enumerate(request.recommendations, start=1)
    )
    lines.append("")

    lines.append("## 六、风险提示")
    lines.append(f"风险等级：{_RISK_LABEL[request.risk_level]}")
    lines.append("")

    lines.append("## 七、数据来源")
    lines.extend(f"- {source}" for source in request.sources)
    lines.append("")
    return "\n".join(lines)


@default_registry.register(
    name="report.generate",
    description=(
        "生成结构化分析报告（问题/数据范围/异常/根因候选+证据/排查顺序/风险/来源），"
        "落库到 reports 表并返回 Markdown。"
    ),
    params_model=ReportRequest,
)
def report_generate(params: ReportRequest, ctx: ToolContext) -> ToolResult:
    if params.equipment_id and not _EQUIPMENT_RE.match(params.equipment_id):
        raise ToolValidationError(f"非法设备编号: {params.equipment_id}")

    generated_at = datetime.now(UTC)
    markdown = render_markdown(params, generated_at)

    with app_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO reports (task_id, report_type, title, equipment_id, "
                "risk_level, status, content_markdown, content_json, created_by) "
                "VALUES (%s, %s, %s, %s, %s, 'draft', %s, %s, 'AI') "
                "RETURNING report_id",
                (
                    params.task_id,
                    params.report_type,
                    params.title,
                    params.equipment_id,
                    params.risk_level,
                    markdown,
                    json.dumps(params.model_dump(), ensure_ascii=False, default=str),
                ),
            )
            report_id = cur.fetchone()[0]
        conn.commit()

    return ToolResult(
        tool="report.generate",
        data={
            "report_id": report_id,
            "title": params.title,
            "risk_level": params.risk_level,
            "markdown": markdown,
        },
        meta={
            "source": "postgres:reports",
            "row_count": 1,
            "report_id": report_id,
        },
    )
