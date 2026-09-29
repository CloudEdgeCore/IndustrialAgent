"""工具注册表：工具定义与查找。"""

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel

from tools.base import ToolContext, ToolNotFoundError, ToolResult


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    params_model: type[BaseModel]
    handler: Callable[[BaseModel, ToolContext], ToolResult]


class ToolRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def register(
        self, name: str, description: str, params_model: type[BaseModel]
    ) -> Callable:
        def decorator(func: Callable[[BaseModel, ToolContext], ToolResult]) -> Callable:
            if name in self._specs:
                raise ValueError(f"工具重复注册: {name}")
            self._specs[name] = ToolSpec(
                name=name,
                description=description,
                params_model=params_model,
                handler=func,
            )
            return func

        return decorator

    def get(self, name: str) -> ToolSpec:
        spec = self._specs.get(name)
        if spec is None:
            raise ToolNotFoundError(f"工具不存在: {name}")
        return spec

    def names(self) -> list[str]:
        return sorted(self._specs)

    def specs(self) -> list[ToolSpec]:
        return [self._specs[name] for name in self.names()]


default_registry = ToolRegistry()
