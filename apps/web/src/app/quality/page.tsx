"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { EChartsOption } from "echarts";

import { EChart } from "@/components/charts/echart";
import { DEFECT_LABELS, KpiCard, SectionCard } from "@/components/ui-bits";
import {
  api,
  type QualitySummary,
  type QualityTrendPoint,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const PRODUCTS = [
  { id: "PRD-A", label: "A 产品" },
  { id: "PRD-B", label: "B 产品" },
  { id: "PRD-C", label: "C 产品" },
];

export default function QualityPage() {
  const [product, setProduct] = useState("PRD-A");
  const [days, setDays] = useState(7);
  const [summary, setSummary] = useState<QualitySummary | null>(null);
  const [trend, setTrend] = useState<QualityTrendPoint[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .qualitySummary(product, days)
      .then(setSummary)
      .catch((err) => setError(String(err)));
  }, [product, days]);

  useEffect(() => {
    api.qualityTrend(product, 14).then(setTrend).catch(() => setTrend([]));
  }, [product]);

  const trendOption: EChartsOption | null = useMemo(() => {
    if (trend.length === 0) return null;
    return {
      grid: { left: 8, right: 16, top: 16, bottom: 8, containLabel: true },
      tooltip: { trigger: "axis", valueFormatter: (value) => `${value}%` },
      xAxis: {
        type: "category",
        data: trend.map((point) => point.date.slice(5)),
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
          data: trend.map((point) => Number((point.fail_rate * 100).toFixed(2))),
          itemStyle: { color: "#6366f1" },
          areaStyle: { color: "#6366f1", opacity: 0.08 },
        },
      ],
    };
  }, [trend]);

  const paretoOption: EChartsOption | null = useMemo(() => {
    if (!summary || summary.top_defects.length === 0) return null;
    const labels = summary.top_defects.map(
      (item) => DEFECT_LABELS[item.defect_type] ?? item.defect_type,
    );
    const counts = summary.top_defects.map((item) => item.count);
    const total = counts.reduce((sum, value) => sum + value, 0) || 1;
    let running = 0;
    const cumulative = counts.map((value) => {
      running += value;
      return Number(((running / total) * 100).toFixed(1));
    });
    return {
      grid: { left: 8, right: 40, top: 24, bottom: 8, containLabel: true },
      tooltip: { trigger: "axis" },
      legend: { top: 0, textStyle: { fontSize: 11 } },
      xAxis: {
        type: "category",
        data: labels,
        axisLabel: { fontSize: 11, color: "#64748b" },
        axisTick: { show: false },
      },
      yAxis: [
        { type: "value", splitLine: { lineStyle: { color: "#f1f5f9" } }, axisLabel: { fontSize: 11, color: "#64748b" } },
        { type: "value", max: 100, axisLabel: { formatter: "{value}%", fontSize: 11, color: "#64748b" }, splitLine: { show: false } },
      ],
      series: [
        {
          name: "缺陷数",
          type: "bar",
          barWidth: 26,
          data: counts,
          itemStyle: { color: "#8b5cf6", borderRadius: [6, 6, 0, 0] },
        },
        {
          name: "累计占比",
          type: "line",
          yAxisIndex: 1,
          data: cumulative,
          itemStyle: { color: "#f59e0b" },
          symbolSize: 5,
        },
      ],
    };
  }, [summary]);

  const equipmentOption: EChartsOption | null = useMemo(() => {
    if (!summary || summary.by_equipment.length === 0) return null;
    return {
      grid: { left: 8, right: 16, top: 16, bottom: 8, containLabel: true },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      xAxis: {
        type: "category",
        data: summary.by_equipment.map((item) => item.equipment_id),
        axisLabel: { fontSize: 11, color: "#64748b" },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: "#f1f5f9" } },
        axisLabel: { fontSize: 11, color: "#64748b" },
      },
      series: [
        {
          type: "bar",
          barWidth: 26,
          data: summary.by_equipment.map((item) => ({
            value: item.count,
            itemStyle: {
              color: item.equipment_id === "EQ-003" ? "#dc2626" : "#6366f1",
              borderRadius: [6, 6, 0, 0],
            },
          })),
        },
      ],
    };
  }, [summary]);

  if (error) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
        加载失败：{error}
      </div>
    );
  }

  const rateUp =
    summary?.baseline_fail_rate != null &&
    summary.fail_rate > summary.baseline_fail_rate * 1.5;
  const aiQuery = `最近 ${days} 天 ${product === "PRD-A" ? "A" : product.slice(-1)} 产品不良率为什么升高？主要缺陷和嫌疑设备是什么？`;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">质量分析</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            不良率趋势 · 缺陷 Pareto · 设备分布与 AI 根因分析
          </p>
        </div>
        <div className="flex gap-2">
          {PRODUCTS.map((item) => (
            <button
              key={item.id}
              onClick={() => setProduct(item.id)}
              className={cn(
                "rounded-full border px-3 py-1.5 text-xs",
                product === item.id
                  ? "border-violet-300 bg-violet-50 text-violet-700"
                  : "text-muted-foreground hover:border-violet-200",
              )}
            >
              {item.label}
            </button>
          ))}
          <span className="mx-1 h-6 w-px bg-border" />
          {[3, 7, 14].map((value) => (
            <button
              key={value}
              onClick={() => setDays(value)}
              className={cn(
                "rounded-full border px-3 py-1.5 text-xs",
                days === value
                  ? "border-violet-300 bg-violet-50 text-violet-700"
                  : "text-muted-foreground hover:border-violet-200",
              )}
            >
              近 {value} 天
            </button>
          ))}
        </div>
      </header>

      {summary ? (
        <div className="grid gap-4 md:grid-cols-4">
          <KpiCard label={`近 ${days} 天检验量`} value={summary.total.toLocaleString()} hint={`产品 ${summary.product_id}`} />
          <KpiCard
            label="合格率"
            value={`${((1 - summary.fail_rate) * 100).toFixed(2)}%`}
            tone="good"
          />
          <KpiCard
            label="不良率"
            value={`${(summary.fail_rate * 100).toFixed(2)}%`}
            hint={
              summary.baseline_fail_rate != null
                ? `基线 ${(summary.baseline_fail_rate * 100).toFixed(2)}%`
                : undefined
            }
            tone={rateUp ? "bad" : "good"}
          />
          <KpiCard label="缺陷数" value={summary.fail_count} hint={`主要缺陷：${DEFECT_LABELS[summary.top_defects[0]?.defect_type ?? ""] ?? "-"}`} tone="warn" />
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-4">
          {[0, 1, 2, 3].map((index) => (
            <div key={index} className="h-28 animate-pulse rounded-xl border bg-muted/40" />
          ))}
        </div>
      )}

      {summary && rateUp ? (
        <SectionCard title="AI Quality Insight" subtitle="基于近 3 天数据的自动洞察">
          <p className="text-sm leading-6">
            {summary.product_id} 不良率过去 {days} 天明显升高（
            <span className="font-semibold text-red-600">
              {(summary.fail_rate * 100).toFixed(2)}%
            </span>
            ，基线 {((summary.baseline_fail_rate ?? 0) * 100).toFixed(2)}%），主要集中：
          </p>
          <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
            <li>设备：{summary.by_equipment[0]?.equipment_id ?? "-"}</li>
            <li>
              缺陷：
              {summary.top_defects
                .slice(0, 2)
                .map((item) => DEFECT_LABELS[item.defect_type] ?? item.defect_type)
                .join(" / ")}
            </li>
          </ul>
          <Link
            href={`/ai?q=${encodeURIComponent(aiQuery)}`}
            className="mt-4 inline-block rounded-md bg-violet-600 px-4 py-2 text-xs font-medium text-white hover:bg-violet-500"
          >
            AI 根因分析
          </Link>
        </SectionCard>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <SectionCard title="不良率趋势" subtitle={`${summary?.product_id ?? "-"} · 近 14 天`}>
          {trendOption ? <EChart option={trendOption} height={260} /> : <p className="py-8 text-center text-sm text-muted-foreground">加载中…</p>}
        </SectionCard>
        <SectionCard title="缺陷 Pareto" subtitle={`近 ${days} 天 · 前 5 类缺陷`}>
          {paretoOption ? <EChart option={paretoOption} height={260} /> : <p className="py-8 text-center text-sm text-muted-foreground">加载中…</p>}
        </SectionCard>
      </div>

      <SectionCard title="不良设备分布" subtitle={`近 ${days} 天 · 前 5 台`}>
        {equipmentOption ? <EChart option={equipmentOption} height={240} /> : <p className="py-8 text-center text-sm text-muted-foreground">加载中…</p>}
      </SectionCard>
    </div>
  );
}
