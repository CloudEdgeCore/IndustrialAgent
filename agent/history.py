"""会话历史渲染（Router 与专业 Agent 共用）。

历史只注入提示词用于理解上下文；上限控制是为了避免上下文膨胀与无谓成本。
"""

_MAX_HISTORY_MESSAGES = 6
_MAX_HISTORY_CHARS = 500


def format_history(history: list[dict] | None) -> str:
    """把会话历史渲染为提示词片段；无有效内容时返回空串。"""
    if not history:
        return ""
    lines: list[str] = []
    for item in history[-_MAX_HISTORY_MESSAGES:]:
        role = "用户" if item.get("role") == "user" else "助手"
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        if len(content) > _MAX_HISTORY_CHARS:
            content = content[:_MAX_HISTORY_CHARS] + "…"
        lines.append(f"{role}：{content}")
    if not lines:
        return ""
    return "历史对话（供理解上下文，勿重复回答）：\n" + "\n".join(lines)
