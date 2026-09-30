"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { RiskBadge } from "@/components/ui-bits";
import { api, type ReportDetail } from "@/lib/api";

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

export default function ReportDetailPage() {
  const params = useParams<{ id: string }>();
  const reportId = params.id as string;
  const [report, setReport] = useState<ReportDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!reportId) return;
    api
      .report(Number(reportId))
      .then(setReport)
      .catch((err) => setError(String(err)));
  }, [reportId]);

  if (error) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
        加载失败：{error}
        <div className="mt-3">
          <Link href="/reports" className="text-violet-600 hover:underline">
            返回报告中心
          </Link>
        </div>
      </div>
    );
  }
  if (!report) {
    return <div className="p-10 text-center text-sm text-muted-foreground">加载报告…</div>;
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
        <Link href="/reports" className="text-sm text-violet-600 hover:underline">
          ← 返回报告中心
        </Link>
        <div className="flex items-center gap-2">
          <a
            href={`/api/reports/${report.report_id}/export`}
            className="rounded-md border px-3 py-1.5 text-xs hover:bg-muted"
            download
          >
            导出 Markdown
          </a>
          <button
            onClick={() => window.print()}
            className="rounded-md border px-3 py-1.5 text-xs hover:bg-muted"
          >
            打印 / 另存 PDF
          </button>
        </div>
      </div>

      <div className="rounded-xl border bg-card p-8">
        <div className="mb-6 flex flex-wrap items-center gap-3 border-b pb-4">
          <span className="font-mono text-xs text-muted-foreground">
            RPT-{report.report_id}
          </span>
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
            {TYPE_LABELS[report.report_type] ?? report.report_type}
          </span>
          {report.equipment_id ? (
            <Link
              href={`/equipment/${report.equipment_id}`}
              className="font-mono text-xs text-violet-600 hover:underline"
            >
              {report.equipment_id}
            </Link>
          ) : null}
          <RiskBadge level={report.risk_level} />
          <span className="ml-auto text-xs text-muted-foreground">
            {formatTime(report.created_at)}
          </span>
        </div>

        <article className="prose-report max-w-none text-sm leading-7 [&_h1]:mb-4 [&_h1]:text-xl [&_h1]:font-semibold [&_h2]:mt-6 [&_h2]:mb-2 [&_h2]:text-base [&_h2]:font-semibold [&_h3]:mt-4 [&_h3]:font-medium [&_li]:my-1 [&_table]:my-3 [&_table]:w-full [&_td]:border [&_td]:border-border [&_td]:px-3 [&_td]:py-1.5 [&_th]:border [&_th]:border-border [&_th]:bg-muted/50 [&_th]:px-3 [&_th]:py-1.5 [&_ul]:list-disc [&_ul]:pl-5">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {report.content_markdown ?? ""}
          </ReactMarkdown>
        </article>
      </div>
    </div>
  );
}
