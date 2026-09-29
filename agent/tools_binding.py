"""Tool 绑定：将 Tool Layer 的 ToolSpec 转换为 OpenAI function-calling schema。

Agent 只能看到权限矩阵内工具（最小权限，架构 §6）。
"""

from typing import Any

from tools.loader import load_all_tools
from tools.permissions import AGENT_PERMISSIONS
from tools.registry import default_registry


def tool_schemas_for_agent(agent_name: str) -> list[dict[str, Any]]:
    load_all_tools()
    allowed = AGENT_PERMISSIONS.get(agent_name, set())
    schemas: list[dict[str, Any]] = []
    for spec in default_registry.specs():
        if spec.name not in allowed:
            continue
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.params_model.model_json_schema(),
                },
            }
        )
    return schemas
