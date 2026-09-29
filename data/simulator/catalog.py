"""fixtures 目录加载器：设备 / 报警 / 缺陷 / 产线 目录。"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def _load(name: str) -> Any:
    with open(FIXTURES_DIR / name, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_equipment() -> list[dict]:
    return _load("equipment.json")


@lru_cache(maxsize=1)
def load_alarm_catalog() -> list[dict]:
    return _load("alarm_catalog.json")


@lru_cache(maxsize=1)
def load_defect_catalog() -> list[dict]:
    return _load("defect_catalog.json")


@lru_cache(maxsize=1)
def load_production() -> dict:
    return _load("production.json")
