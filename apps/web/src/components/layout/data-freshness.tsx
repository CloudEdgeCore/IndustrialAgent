"use client";

import { useEffect, useState } from "react";

import { api, type Freshness } from "@/lib/api";
import { cn } from "@/lib/utils";

/** 滞后阈值：超过该小时数视为"数据陈旧"，界面转为告警色。 */
const STALE_HOURS = 24;

function formatLag(hours: number): string {
  if (hours < 1) return "刚刚";
  if (hours < 48) return `${hours.toFixed(1)} 小时前`;
  return `${(hours / 24).toFixed(1)} 天前`;
}

/**
 * 全局数据新鲜度指示：明确告知分析窗口的数据截止时间。
 *
 * 相对时间窗口锚定在数据末尾时，必须让"数据截至"可见，否则数天前的读数
 * 会被误读为实时监控数据。
 */
export function DataFreshnessBar() {
  const [info, setInfo] = useState<Freshness | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .freshness()
      .then((value) => {
        if (alive) setInfo(value);
      })
      .catch(() => {
        if (alive) setFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  if (failed || !info) return null;

  const stale = info.lag_hours > STALE_HOURS;
  const asOf = new Date(info.anchor).toLocaleString("zh-CN", { hour12: false });

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs",
        stale
          ? "border-amber-200 bg-amber-50 text-amber-700"
          : "border-emerald-200 bg-emerald-50 text-emerald-700",
      )}
      title={`窗口锚点来源：${info.resolved_from === "data" ? "数据末尾" : "真实时钟"}（WINDOW_ANCHOR）`}
    >
      <span
        className={cn(
          "size-1.5 rounded-full",
          stale ? "bg-amber-500" : "bg-emerald-500",
        )}
      />
      数据截至 {asOf}
      <span className="text-muted-foreground">· 滞后 {formatLag(info.lag_hours)}</span>
    </span>
  );
}
