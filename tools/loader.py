"""工具加载器：import 各工具模块以触发注册（P3 Agent 启动时调用）。"""

_loaded = False


def load_all_tools() -> None:
    global _loaded
    if _loaded:
        return
    from tools.sql import (
        domain,  # noqa: F401
        tool,  # noqa: F401
    )
    from tools.timeseries import tool as timeseries_tool  # noqa: F401

    _loaded = True
