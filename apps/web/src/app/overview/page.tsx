"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { EChartsOption } from "echarts";

import { EChart } from "@/components/charts/echart";
import { KpiCard, RiskBadge, SectionCard } from "@/components/ui-bits";
import {
  api,
  type Alarm,
  type Equipment,
  type QualitySummary,
  type QualityTrendPoint,
  type ReportInfo,
} from "@/lib/api";

type OverviewData = {
  equipment: Equipment[];
  alarms: Alarm[];
  quality: QualitySummary;
  trend: QualityTrendPoint[];
  reports: ReportInfo[];
};

function formatTime(value: string): string {
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

export default function OverviewPage() {
  const [data, setData] = useState<OverviewData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [equipmentRes, alarms, quality, trend, reportsRes] = await Promise.all([
          api.equipmentList(),
          api.alarms({ status: "active", limit: 20 }),
          api.qualitySummary("PRD-A", 3),
          api.qualityTrend("PRD-A", 14),
          api.reports(6),
        ]);
        setData({
          equipment: equipmentRes.items,
          alarms,
          quality,
          trend,
          reports: reportsRes.items,
        });
      } catch (err) {
        setError(String(err));
      }
    })();
  }, []);

  const stats = useMemo(() => {
    if (!data) return null;
    const byStatus = { running: 0, attention: 0, alarm: 0, stopped: 0 } as Record<string, number>;
    for (const item of data.equipment) {
      byStatus[item.status] = (byStatus[item.status] ?? 0) + 1;
    }
    const lowest = [...data.equipment]
      .sort((a, b) => a.health_score - b.health_score)
      .slice(0, 6);
    const rateUp =
      data.quality.baseline_fail_rate != null &&
      data.quality.fail_rate > data.quality.baseline_fail_rate * 1.5;
    return { byStatus, lowest, rateUp };
  }, [data]);

  const healthOption: EChartsOption | null = useMemo(() => {
    if (!stats) return null;
    return {
      grid: { left: 8, right: 24, top: 8, bottom: 8, containLabel: true },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      xAxis: { type: "value", max: 100, splitLine: { lineStyle: { color: "#f1f5f9" } } },
      yAxis: {
        type: "category",
        data: stats.lowest.map((item) => item.name),
        axisTick: { show: false },
        axisLine: { show: false },
        axisLabel: { fontSize: 11, color: "#64748b" },
      },
      series: [
        {
          type: "bar",
          barWidth: 12,
          itemStyle: {
            borderRadius: [0, 6, 6, 0],
          },
          data: stats.lowest.map((item) => ({
            value: item.health_score,
            itemStyle: {
              color:
                item.status === "alarm"
                  ? "#dc2626"
                  : item.status === "stopped" || item.health_score < 80
                    ? "#f59e0b"
                    : "#10b981",
            },
          })),
        },
      ],
    };
  }, [stats]);

  const trendOption: EChartsOption | null = useMemo(() => {
    if (!data) return null;
    return {
      grid: { left: 8, right: 16, top: 16, bottom: 8, containLabel: true },
      tooltip: {
        trigger: "axis",
        valueFormatter: (value) => `${value}%`,
      },
      xAxis: {
        type: "category",
        data: data.trend.map((point) => point.date.slice(5)),
        axisLabel: { fontSize: 11, color: "#64748b" },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        axisLabel: { formatter: "{value}%", fontSize: 11, color: "#64748b" },
        splitLine: { lineStyle: { color: "#f1f5f9" } },
      },
      series: [
        {
          type: "line",
          smooth: true,
          symbolSize: 5,
          data: data.trend.map((point) => Number((point.fail_rate * 100).toFixed(2))),
          itemStyle: { color: "#6366f1" },
          areaStyle: { color: "#6366f1", opacity: 0.08 },
          markLine: data.quality.baseline_fail_rate
            ? {
                silent: true,
                symbol: "none",
                data: [
                  {
                    yAxis: Number((data.quality.baseline_fail_rate * 100).toFixed(2)),
                    lineStyle: { type: "dashed", color: "#94a3b8" },
                    label: { formatter: "基线", color: "#64748b", fontSize: 10 },
                  },
                ],
              }
            : undefined,
        },
      ],
    };
  }, [data]);

  if (error) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
        加载失败：{error}
      </div>
    );
  }
  if (!data || !stats) {
    return <div className="p-10 text-center text-sm text-muted-foreground">加载工厂总览…</div>;
  }

  const riskItems: { key: string; title: string; desc: string; query: string }[] = [];
  for (const alarm of data.alarms.slice(0, 2)) {
    riskItems.push({
      key: `alarm-${alarm.equipment_id}-${alarm.alarm_code}`,
      title: `${alarm.equipment_name ?? alarm.equipment_id} · ${alarm.alarm_code}`,
      desc: alarm.description ?? "活跃报警",
      query: `${alarm.equipment_id} 出现 ${alarm.alarm_code} 报警，帮我分析原因。`,
    });
  }
  if (stats.rateUp) {
    riskItems.push({
      key: "quality",
      title: `A 产品不良率 ${(data.quality.fail_rate * 100).toFixed(1)}%（基线 ${((data.quality.baseline_fail_rate ?? 0) * 100).toFixed(1)}%）`,
      desc: `近 3 天不良集中于 ${data.quality.by_equipment[0]?.equipment_id ?? "-"} / ${data.quality.top_defects[0]?.defect_type ?? "-"}`,
      query: "最近 3 天 A 产品不良率为什么升高？",
    });
  }
  for (const item of data.equipment.filter((eq) => eq.status === "attention").slice(0, 1)) {
    riskItems.push({
      key: `attention-${item.equipment_id}`,
      title: `${item.name} 处于关注状态`,
      desc: `健康度 ${item.health_score}，建议检查近期振动数据`,
      query: `检查 ${item.equipment_id} 最近的运行数据是否异常。`,
    });
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          工厂总览 · 设备健康、质量趋势与 AI 风险摘要
        </p>
      </header>

      <div className="grid gap-4 md:grid-cols-4">
        <KpiCard
          label="设备总数"
          value={data.equipment.length}
          hint={`运行 ${stats.byStatus.running} · 关注 ${stats.byStatus.attention}`}
        />
        <KpiCard
          label="告警 / 停机"
          value={`${stats.byStatus.alarm} / ${stats.byStatus.stopped}`}
          hint={`活跃报警 ${data.alarms.length} 条`}
          tone={stats.byStatus.alarm > 0 ? "bad" : "good"}
        />
        <KpiCard
          label="近 3 天不良率（A 产品）"
          value={`${(data.quality.fail_rate * 100).toFixed(1)}%`}
          hint={
            data.quality.baseline_fail_rate != null
              ? `基线 ${(data.quality.baseline_fail_rate * 100).toFixed(1)}%`
              : undefined
          }
          tone={stats.rateUp ? "bad" : "good"}
        />
        <KpiCard
          label="AI 分析报告"
          value={data.reports.length}
          hint="最近生成的分析与诊断报告"
          tone="ai"
        />
      </div>

      <SectionCard
        title="AI 风险摘要"
        subtitle="AI 发现以下需要关注的问题（点击立即分析，跳转 AI 诊断）"
      >
        {riskItems.length === 0 ? (
          <p className="text-sm text-muted-foreground">当前无显著风险项。</p>
        ) : (
          <ul className="space-y-3">
            {riskItems.map((item) => (
              <li key={item.key} className="flex items-center justify-between gap-4 rounded-lg border bg-muted/30 px-4 py-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 text-sm font-medium">
                    <span className="size-1.5 rounded-full bg-violet-500" />
                    {item.title}
                  </div>
                  <div className="mt-0.5 truncate text-xs text-muted-foreground">{item.desc}</div>
                </div>
                <Link
                  href={`/ai?q=${encodeURIComponent(item.query)}`}
                  className="shrink-0 rounded-md bg-violet-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-500"
                >
                  立即分析
                </Link>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      <div className="grid gap-4 lg:grid-cols-2">
        <SectionCard title="设备健康度" subtitle="健康度最低的 6 台设备">
          {healthOption ? <EChart option={healthOption} height={240} /> : null}
        </SectionCard>
        <SectionCard title="不良率趋势" subtitle="A 产品 · 近 14 天">
          {trendOption ? <EChart option={trendOption} height={240} /> : null}
        </SectionCard>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <SectionCard title="活跃报警" subtitle={`共 ${data.alarms.length} 条`}>
          <ul className="space-y-2">
            {data.alarms.slice(0, 5).map((alarm) => (
              <li
                key={`${alarm.equipment_id}-${alarm.alarm_code}-${alarm.occurred_at}`}
                className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2"
              >
                <div className="flex min-w-0 items-center gap-2">
                  <span
                    className={`size-2 shrink-0 rounded-full ${
                      alarm.severity === "critical"
                        ? "bg-red-500"
                        : alarm.severity === "warning"
                          ? "bg-amber-500"
                          : "bg-slate-400"
                    }`}
                  />
                  <span className="truncate text-sm">
                    {alarm.equipment_name ?? alarm.equipment_id} · {alarm.alarm_code}
                  </span>
                </div>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {formatTime(alarm.occurred_at)}
                </span>
              </li>
            ))}
            {data.alarms.length === 0 ? (
              <p className="text-sm text-muted-foreground">暂无活跃报警。</p>
            ) : null}
          </ul>
        </SectionCard>

        <SectionCard title="最近 AI 分析" subtitle="诊断 / 分析报告">
          <ul className="space-y-2">
            {data.reports.slice(0, 5).map((report) => (
              <li key={report.report_id}>
                <Link
                  href={`/reports/${report.report_id}`}
                  className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2 hover:bg-muted/40"
                >
                  <span className="min-w-0 flex-1 truncate text-sm">{report.title}</span>
                  <RiskBadge level={report.risk_level} />
                </Link>
              </li>
            ))}
            {data.reports.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                暂无报告，可在 AI 诊断中生成。
              </p>
            ) : null}
          </ul>
        </SectionCard>
      </div>
    </div>
  );
}
