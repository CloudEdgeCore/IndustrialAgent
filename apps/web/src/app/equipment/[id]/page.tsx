"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import type { EChartsOption } from "echarts";

import { EChart } from "@/components/charts/echart";
import { SectionCard, StatusBadge } from "@/components/ui-bits";
import {
  api,
  type Alarm,
  type EquipmentDetail,
  type MaintenanceRecord,
  type SensorPoint,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const SENSOR_META: Record<string, { label: string; unit: string }> = {
  temperature: { label: "温度", unit: "℃" },
  pressure: { label: "压力", unit: "bar" },
  speed: { label: "转速", unit: "rpm" },
  vibration: { label: "振动", unit: "mm/s" },
  current: { label: "电流", unit: "A" },
  flow: { label: "冷却液流量", unit: "L/min" },
};

const TABS = [
  { id: "monitor", label: "实时监控" },
  { id: "trend", label: "趋势分析" },
  { id: "alarms", label: "告警" },
  { id: "maintenance", label: "维修记录" },
];

function formatTime(value: string): string {
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

export default function EquipmentDetailPage() {
  const params = useParams<{ id: string }>();
  const equipmentId = params.id as string;
  const [detail, setDetail] = useState<EquipmentDetail | null>(null);
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [maintenance, setMaintenance] = useState<MaintenanceRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState("monitor");
  const [sensor, setSensor] = useState("temperature");
  const [hours, setHours] = useState(24);
  const [readings, setReadings] = useState<SensorPoint[]>([]);

  useEffect(() => {
    if (!equipmentId) return;
    Promise.all([
      api.equipmentDetail(equipmentId),
      api.alarms({ equipment_id: equipmentId, limit: 30 }),
      api.equipmentMaintenance(equipmentId),
    ])
      .then(([detailData, alarmData, maintenanceData]) => {
        setDetail(detailData);
        setAlarms(alarmData);
        setMaintenance(maintenanceData);
      })
      .catch((err) => setError(String(err)));
  }, [equipmentId]);

  useEffect(() => {
    if (!equipmentId) return;
    api
      .equipmentReadings(equipmentId, sensor, hours)
      .then(setReadings)
      .catch(() => setReadings([]));
  }, [equipmentId, sensor, hours]);

  const chartOption: EChartsOption | null = useMemo(() => {
    if (readings.length === 0) return null;
    const meta = SENSOR_META[sensor] ?? { label: sensor, unit: "" };
    return {
      grid: { left: 8, right: 16, top: 24, bottom: 8, containLabel: true },
      tooltip: {
        trigger: "axis",
        valueFormatter: (value) => `${value} ${meta.unit}`,
      },
      xAxis: {
        type: "category",
        data: readings.map((point) =>
          new Date(point.timestamp).toLocaleTimeString("zh-CN", {
            hour12: false,
            hour: "2-digit",
            minute: "2-digit",
          }),
        ),
        axisLabel: { fontSize: 10, color: "#64748b" },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        name: meta.unit,
        nameTextStyle: { fontSize: 10, color: "#94a3b8" },
        splitLine: { lineStyle: { color: "#f1f5f9" } },
        axisLabel: { fontSize: 10, color: "#64748b" },
      },
      series: [
        {
          type: "line",
          smooth: true,
          showSymbol: false,
          data: readings.map((point) => point.value),
          itemStyle: { color: "#6366f1" },
          areaStyle: { color: "#6366f1", opacity: 0.06 },
        },
      ],
    };
  }, [readings, sensor]);

  if (error) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
        加载失败：{error}
      </div>
    );
  }
  if (!detail) {
    return <div className="p-10 text-center text-sm text-muted-foreground">加载设备详情…</div>;
  }

  const aiQuery = `分析 ${equipmentId} 最近的运行数据，判断是否存在异常并给出排查建议。`;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-semibold tracking-tight">{detail.name}</h1>
              <StatusBadge status={detail.status} />
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              {detail.equipment_id} · {detail.model ?? "-"} · {detail.production_line}
            </p>
          </div>
          <div className="rounded-xl border bg-card px-5 py-3 text-center">
            <div className="text-xs text-muted-foreground">Health</div>
            <div
              className={cn(
                "text-2xl font-semibold tabular-nums",
                detail.health_score >= 85
                  ? "text-emerald-600"
                  : detail.health_score >= 70
                    ? "text-amber-600"
                    : "text-red-600",
              )}
            >
              {detail.health_score}
            </div>
          </div>
        </div>
        <Link
          href={`/ai?q=${encodeURIComponent(aiQuery)}`}
          className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500"
        >
          AI 诊断
        </Link>
      </header>

      {detail.active_alarms.length > 0 ? (
        <div className="rounded-xl border border-red-200 bg-red-50 px-5 py-4">
          <div className="text-sm font-semibold text-red-700">
            当前活跃报警（{detail.active_alarms.length}）
          </div>
          <ul className="mt-2 space-y-1">
            {detail.active_alarms.map((alarm) => (
              <li key={`${alarm.alarm_code}-${alarm.occurred_at}`} className="text-xs text-red-700">
                {alarm.alarm_code} · {alarm.description} · {formatTime(alarm.occurred_at)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="flex gap-1 rounded-lg border bg-muted/30 p-1">
        {TABS.map((item) => (
          <button
            key={item.id}
            onClick={() => setTab(item.id)}
            className={cn(
              "rounded-md px-4 py-1.5 text-sm",
              tab === item.id
                ? "bg-card font-medium shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === "monitor" ? (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-6">
            {Object.entries(detail.latest_readings).map(([key, value]) => {
              const meta = SENSOR_META[key] ?? { label: key, unit: "" };
              return (
                <div key={key} className="rounded-xl border bg-card p-4">
                  <div className="text-xs text-muted-foreground">{meta.label}</div>
                  <div className="mt-1 text-lg font-semibold tabular-nums">
                    {value}
                    <span className="ml-1 text-xs font-normal text-muted-foreground">
                      {meta.unit}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
          <SectionCard title="多指标趋势（5 分钟聚合）" subtitle={`${SENSOR_META[sensor]?.label ?? sensor} · 近 ${hours} 小时`}>
            <div className="mb-3 flex flex-wrap gap-2">
              {Object.keys(detail.latest_readings).map((key) => (
                <button
                  key={key}
                  onClick={() => setSensor(key)}
                  className={cn(
                    "rounded-full border px-3 py-1 text-xs",
                    sensor === key
                      ? "border-violet-300 bg-violet-50 text-violet-700"
                      : "text-muted-foreground hover:border-violet-200",
                  )}
                >
                  {SENSOR_META[key]?.label ?? key}
                </button>
              ))}
            </div>
            {chartOption ? (
              <EChart option={chartOption} height={300} />
            ) : (
              <p className="py-10 text-center text-sm text-muted-foreground">暂无数据</p>
            )}
          </SectionCard>
        </div>
      ) : null}

      {tab === "trend" ? (
        <SectionCard title="趋势分析" subtitle={`${SENSOR_META[sensor]?.label ?? sensor}`}>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            {Object.keys(SENSOR_META).map((key) => (
              <button
                key={key}
                onClick={() => setSensor(key)}
                className={cn(
                  "rounded-full border px-3 py-1 text-xs",
                  sensor === key
                    ? "border-violet-300 bg-violet-50 text-violet-700"
                    : "text-muted-foreground hover:border-violet-200",
                )}
              >
                {SENSOR_META[key].label}
              </button>
            ))}
            <span className="mx-2 h-4 w-px bg-border" />
            {[24, 72, 168].map((value) => (
              <button
                key={value}
                onClick={() => setHours(value)}
                className={cn(
                  "rounded-full border px-3 py-1 text-xs",
                  hours === value
                    ? "border-violet-300 bg-violet-50 text-violet-700"
                    : "text-muted-foreground hover:border-violet-200",
                )}
              >
                {value === 24 ? "24 小时" : value === 72 ? "3 天" : "7 天"}
              </button>
            ))}
          </div>
          {chartOption ? (
            <EChart option={chartOption} height={420} />
          ) : (
            <p className="py-10 text-center text-sm text-muted-foreground">暂无数据</p>
          )}
        </SectionCard>
      ) : null}

      {tab === "alarms" ? (
        <SectionCard title="告警记录" subtitle={`最近 ${alarms.length} 条`}>
          <ul className="space-y-2">
            {alarms.map((alarm) => (
              <li
                key={`${alarm.alarm_code}-${alarm.occurred_at}`}
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
                  <span className="text-sm font-medium">{alarm.alarm_code}</span>
                  <span className="truncate text-xs text-muted-foreground">
                    {alarm.description}
                  </span>
                </div>
                <div className="flex shrink-0 items-center gap-3 text-xs text-muted-foreground">
                  <span>{alarm.status === "active" ? "活跃" : alarm.status === "cleared" ? "已清除" : "已确认"}</span>
                  <span>{formatTime(alarm.occurred_at)}</span>
                </div>
              </li>
            ))}
            {alarms.length === 0 ? (
              <p className="text-sm text-muted-foreground">暂无告警记录。</p>
            ) : null}
          </ul>
        </SectionCard>
      ) : null}

      {tab === "maintenance" ? (
        <SectionCard title="维修记录" subtitle={`最近 ${maintenance.length} 条`}>
          <ul className="space-y-3">
            {maintenance.map((record) => (
              <li key={record.id} className="rounded-lg border px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-medium">{record.description}</span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {formatTime(record.occurred_at)}
                  </span>
                </div>
                <div className="mt-1 space-y-0.5 text-xs text-muted-foreground">
                  {record.root_cause ? <div>根因：{record.root_cause}</div> : null}
                  {record.actions ? <div>措施：{record.actions}</div> : null}
                  <div>
                    {record.maintenance_type === "corrective" ? "故障维修" : "预防保养"}
                    {record.technician ? ` · ${record.technician}` : ""}
                  </div>
                </div>
              </li>
            ))}
            {maintenance.length === 0 ? (
              <p className="text-sm text-muted-foreground">暂无维修记录。</p>
            ) : null}
          </ul>
        </SectionCard>
      ) : null}
    </div>
  );
}
