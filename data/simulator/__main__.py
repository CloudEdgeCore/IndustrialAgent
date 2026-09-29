"""CLI：生成并载入工业模拟数据。

用法（仓库根目录）：
    python -m data.simulator                      # 默认 seed=42，7 天时序
    python -m data.simulator --days 2 --quality-days 5 --seed 42   # CI / 快速
"""

import argparse
import json
import os
import time
from datetime import datetime

from data.simulator import generator, loader
from data.simulator.catalog import FIXTURES_DIR


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="工业数据模拟器（固定随机种子，可复现）"
    )
    parser.add_argument("--seed", type=int, default=42, help="随机种子（默认 42）")
    parser.add_argument("--days", type=int, default=7, help="时序数据天数（1 分钟分辨率）")
    parser.add_argument("--quality-days", type=int, default=30, help="质量数据天数")
    parser.add_argument("--history-days", type=int, default=60, help="报警/维修历史天数")
    parser.add_argument(
        "--anchor",
        type=str,
        default=None,
        help="数据截止时间（ISO8601，默认当前 UTC 时间）",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="默认取 DATABASE_URL 环境变量，否则本地默认连接串",
    )
    parser.add_argument(
        "--manifest",
        type=str,
        default=str(FIXTURES_DIR / "manifest.json"),
        help="场景清单输出路径（供集成测试使用）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    anchor = generator.resolve_anchor(
        datetime.fromisoformat(args.anchor) if args.anchor else None
    )
    database_url = args.database_url or os.environ.get(
        "DATABASE_URL", loader.DEFAULT_DATABASE_URL
    )

    started_at = time.perf_counter()
    data = {
        "equipment": generator.build_equipment(),
        "defects": list(generator.iter_defect_rows()),
        "alarms": generator.build_alarms(args.seed, anchor, args.history_days),
        "maintenance_records": None,  # 依赖 alarms，下方填充
        "product_batches": None,  # 依赖质量生成，下方填充
        "quality_inspections": None,
        "sensor_readings": generator.iter_sensor_rows(args.seed, anchor, args.days),
        "process_parameters": generator.iter_process_rows(args.seed, anchor, args.days),
    }
    data["maintenance_records"] = generator.build_maintenance(
        args.seed, anchor, args.history_days, data["alarms"]
    )
    batches, inspections = generator.build_batches_and_inspections(
        args.seed, anchor, args.quality_days
    )
    data["product_batches"] = batches
    data["quality_inspections"] = inspections

    counts = loader.load_all(database_url, data)
    elapsed = time.perf_counter() - started_at

    manifest = generator.build_manifest(
        args.seed, anchor, args.days, args.quality_days, args.history_days, counts
    )
    manifest_path = os.path.abspath(args.manifest)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"seed={args.seed}  anchor={anchor.isoformat()}  耗时 {elapsed:.1f}s")
    for table, n in counts.items():
        print(f"  {table:<22} {n:>9,}")
    print(f"manifest -> {manifest_path}")


if __name__ == "__main__":
    main()
