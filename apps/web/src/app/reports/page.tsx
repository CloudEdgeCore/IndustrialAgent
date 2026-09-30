"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { RiskBadge, SectionCard } from "@/components/ui-bits";
import { api, type ReportInfo } from "@/lib/api";

const TYPE_LABELS: Record<string, string> = {
  equipment_diagnosis: "设备故障诊断",
  process_analysis: "工艺异常分析",
  quality_analysis: "质量问题分析",
  daily: "日报",
  weekly: "周报",
};

function formatTime(value: string): string {
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

export default function ReportsPage() {
  const [reports, setReports] = useState<ReportInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .reports(50)
      .then((response) => setReports(response.items))
      .catch((err) => setError(String(err)));
  }, []);

  if (error) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
        加载失败：{error}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">报告中心</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          由 AI 诊断生成的结构化分析报告（支持 Markdown 导出与打印）
        </p>
      </header>

      <SectionCard title="分析报告" subtitle={`共 ${reports?.length ?? "-"} 份`}>
        {!reports ? (
          <p className="py-6 text-center text-sm text-muted-foreground">加载中…</p>
        ) : reports.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            暂无报告，前往「AI 诊断」提问并生成报告。
          </p>
        ) : (
          <ul className="space-y-2">
            {reports.map((report) => (
              <li key={report.report_id}>
                <Link
                  href={`/reports/${report.report_id}`}
                  className="flex flex-wrap items-center gap-3 rounded-lg border px-4 py-3 hover:bg-muted/30"
                >
                  <span className="font-mono text-xs text-muted-foreground">
                    #{report.report_id}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-sm font-medium">
                    {report.title}
                  </span>
                  <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                    {TYPE_LABELS[report.report_type] ?? report.report_type}
                  </span>
                  {report.equipment_id ? (
                    <span className="font-mono text-xs text-muted-foreground">
                      {report.equipment_id}
                    </span>
                  ) : null}
                  <RiskBadge level={report.risk_level} />
                  <span className="text-xs text-muted-foreground">
                    {formatTime(report.created_at)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
    </div>
  );
}
