"use client";

import { useEffect, useMemo, useState } from "react";

import { SectionCard } from "@/components/ui-bits";
import { api, type DocumentInfo, type SearchHit } from "@/lib/api";
import { cn } from "@/lib/utils";

const TYPE_LABELS: Record<string, string> = {
  manual: "设备手册",
  sop: "SOP",
  alarm_code: "报警代码",
  quality: "质量规范",
  maintenance: "维修规范",
  standard: "标准",
};

const TYPE_FILTERS = [
  { id: "", label: "全部文档" },
  { id: "manual", label: "设备手册" },
  { id: "sop", label: "SOP" },
  { id: "quality", label: "质量规范" },
  { id: "maintenance", label: "维修规范" },
  { id: "alarm_code", label: "报警代码" },
];

export default function KnowledgePage() {
  const [documents, setDocuments] = useState<DocumentInfo[] | null>(null);
  const [filter, setFilter] = useState("");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  useEffect(() => {
    api
      .documents()
      .then(setDocuments)
      .catch(() => setDocuments([]));
  }, []);

  async function search() {
    if (!query.trim()) return;
    setSearching(true);
    setSearchError(null);
    try {
      const results = await api.searchKnowledge(query, 5);
      setHits(results);
    } catch (err) {
      setSearchError(String(err));
      setHits([]);
    } finally {
      setSearching(false);
    }
  }

  const filtered = useMemo(() => {
    if (!documents) return [];
    if (!filter) return documents;
    return documents.filter((doc) => doc.document_type === filter);
  }, [documents, filter]);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">知识库</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          设备说明书 · SOP · 报警代码 · 质量规范（RAG 混合检索，带引用来源）
        </p>
      </header>

      <SectionCard title="知识检索" subtitle="向量 + 关键词混合检索（引用可溯源）">
        <div className="flex gap-3">
          <input
            className="flex-1 rounded-lg border px-4 py-2.5 text-sm outline-none focus:border-violet-400"
            placeholder="例如：E102 报警怎么处理 / 表面裂纹判定标准"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void search();
            }}
          />
          <button
            onClick={() => void search()}
            disabled={searching || !query.trim()}
            className="rounded-lg bg-violet-600 px-5 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-40"
          >
            {searching ? "检索中…" : "检索"}
          </button>
        </div>

        {searchError ? (
          <p className="mt-3 text-xs text-red-600">{searchError}</p>
        ) : null}

        {hits ? (
          <ul className="mt-4 space-y-3">
            {hits.map((hit) => (
              <li key={`${hit.document_title}-${hit.chunk_index}`} className="rounded-lg border p-4">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="rounded-full bg-violet-50 px-2 py-0.5 font-medium text-violet-700">
                    {hit.document_title}
                  </span>
                  {hit.section ? (
                    <span className="text-muted-foreground">§ {hit.section}</span>
                  ) : null}
                  <span className="text-muted-foreground">
                    {TYPE_LABELS[hit.document_type] ?? hit.document_type}
                    {hit.version ? ` · ${hit.version}` : ""}
                  </span>
                  <span className="ml-auto text-muted-foreground">
                    相关度 {Number(hit.scores.rerank ?? 0).toFixed(3)}
                  </span>
                </div>
                <p className="mt-2 whitespace-pre-line text-sm leading-6 text-foreground/90">
                  {hit.content.length > 360 ? `${hit.content.slice(0, 360)}…` : hit.content}
                </p>
              </li>
            ))}
            {hits.length === 0 ? (
              <p className="text-sm text-muted-foreground">未找到相关内容。</p>
            ) : null}
          </ul>
        ) : null}
      </SectionCard>

      <div className="flex flex-wrap gap-2">
        {TYPE_FILTERS.map((item) => (
          <button
            key={item.id}
            onClick={() => setFilter(item.id)}
            className={cn(
              "rounded-full border px-3 py-1.5 text-xs",
              filter === item.id
                ? "border-violet-300 bg-violet-50 text-violet-700"
                : "text-muted-foreground hover:border-violet-200",
            )}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="overflow-hidden rounded-xl border bg-card">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
              <th className="px-4 py-3 font-medium">文档</th>
              <th className="px-4 py-3 font-medium">类型</th>
              <th className="px-4 py-3 font-medium">适用设备</th>
              <th className="px-4 py-3 font-medium">版本</th>
              <th className="px-4 py-3 font-medium">分块</th>
              <th className="px-4 py-3 font-medium">状态</th>
            </tr>
          </thead>
          <tbody>
            {!documents ? (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-muted-foreground">
                  加载中…
                </td>
              </tr>
            ) : (
              filtered.map((doc) => (
                <tr key={doc.document_id} className="border-b last:border-0 hover:bg-muted/30">
                  <td className="px-4 py-3">{doc.title}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {TYPE_LABELS[doc.document_type] ?? doc.document_type}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {doc.equipment_type ?? "通用"}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{doc.version ?? "-"}</td>
                  <td className="px-4 py-3 tabular-nums text-muted-foreground">
                    {doc.chunk_count}
                  </td>
                  <td className="px-4 py-3">
                    <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs text-emerald-700">
                      {doc.status === "indexed" ? "已索引" : doc.status}
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
