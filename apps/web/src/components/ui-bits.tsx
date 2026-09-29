import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function KpiCard({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "default" | "good" | "warn" | "bad" | "ai";
}) {
  const toneClass = {
    default: "text-foreground",
    good: "text-emerald-600",
    warn: "text-amber-600",
    bad: "text-red-600",
    ai: "text-violet-600",
  }[tone];
  return (
    <div className="rounded-xl border bg-card p-5">
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className={cn("mt-2 text-2xl font-semibold tabular-nums", toneClass)}>
        {value}
      </div>
      {hint ? <div className="mt-1 text-xs text-muted-foreground">{hint}</div> : null}
    </div>
  );
}

const STATUS_MAP: Record<string, { label: string; className: string }> = {
  running: { label: "正常", className: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  attention: { label: "关注", className: "bg-amber-50 text-amber-700 border-amber-200" },
  alarm: { label: "告警", className: "bg-red-50 text-red-700 border-red-200" },
  stopped: { label: "停机", className: "bg-gray-100 text-gray-600 border-gray-200" },
};

export function StatusBadge({ status }: { status: string }) {
  const item = STATUS_MAP[status] ?? {
    label: status,
    className: "bg-muted text-muted-foreground border-border",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-xs",
        item.className,
      )}
    >
      {item.label}
    </span>
  );
}

const RISK_MAP: Record<string, { label: string; className: string }> = {
  low: { label: "低风险", className: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  medium: { label: "中风险", className: "bg-amber-50 text-amber-700 border-amber-200" },
  high: { label: "高风险", className: "bg-red-50 text-red-700 border-red-200" },
  critical: { label: "严重", className: "bg-red-100 text-red-800 border-red-300" },
};

export function RiskBadge({ level }: { level: string | null | undefined }) {
  if (!level) return null;
  const item = RISK_MAP[level] ?? {
    label: level,
    className: "bg-muted text-muted-foreground border-border",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-xs",
        item.className,
      )}
    >
      {item.label}
    </span>
  );
}

export function SectionCard({
  title,
  subtitle,
  action,
  children,
  className,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("rounded-xl border bg-card p-5", className)}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">{title}</h2>
          {subtitle ? (
            <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>
          ) : null}
        </div>
        {action}
      </div>
      {children}
    </div>
  );
}

export const DEFECT_LABELS: Record<string, string> = {
  surface_crack: "表面裂纹",
  dimension_deviation: "尺寸偏差",
  burr: "毛刺",
  porosity: "气孔",
  scratch: "划痕",
  color_deviation: "色差",
};

export const EQUIPMENT_TYPE_LABELS: Record<string, string> = {
  cnc: "数控加工中心",
  injection_molding: "注塑机",
  assembly_line: "装配工位",
};
