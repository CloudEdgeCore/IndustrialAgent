"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { EQUIPMENT_TYPE_LABELS, StatusBadge } from "@/components/ui-bits";
import { api, type Equipment } from "@/lib/api";

export default function EquipmentPage() {
  const [items, setItems] = useState<Equipment[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [keyword, setKeyword] = useState("");

  useEffect(() => {
    api
      .equipmentList()
      .then((response) => setItems(response.items))
      .catch((err) => setError(String(err)));
  }, []);

  const filtered = useMemo(() => {
    if (!items) return [];
    return items.filter((item) => {
      if (typeFilter && item.equipment_type !== typeFilter) return false;
      if (statusFilter && item.status !== statusFilter) return false;
      if (keyword && !`${item.name}${item.equipment_id}${item.model ?? ""}`.toLowerCase().includes(keyword.toLowerCase()))
        return false;
      return true;
    });
  }, [items, typeFilter, statusFilter, keyword]);

  if (error) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
        加载失败：{error}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">设备中心</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            设备列表 · 状态监控与健康度（共 {items?.length ?? "-"} 台）
          </p>
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-3">
        <input
          className="w-56 rounded-md border px-3 py-2 text-sm outline-none focus:border-violet-400"
          placeholder="搜索设备名称 / 编号"
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
        />
        <select
          className="rounded-md border px-3 py-2 text-sm"
          value={typeFilter}
          onChange={(event) => setTypeFilter(event.target.value)}
        >
          <option value="">全部类型</option>
          {Object.entries(EQUIPMENT_TYPE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <select
          className="rounded-md border px-3 py-2 text-sm"
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value)}
        >
          <option value="">全部状态</option>
          <option value="running">正常</option>
          <option value="attention">关注</option>
          <option value="alarm">告警</option>
          <option value="stopped">停机</option>
        </select>
        <span className="text-xs text-muted-foreground">共 {filtered.length} 台</span>
      </div>

      <div className="overflow-hidden rounded-xl border bg-card">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
              <th className="px-4 py-3 font-medium">设备名称</th>
              <th className="px-4 py-3 font-medium">编号</th>
              <th className="px-4 py-3 font-medium">类型</th>
              <th className="px-4 py-3 font-medium">产线</th>
              <th className="px-4 py-3 font-medium">状态</th>
              <th className="px-4 py-3 font-medium">健康度</th>
              <th className="px-4 py-3 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {!items ? (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-muted-foreground">
                  加载中…
                </td>
              </tr>
            ) : (
              filtered.map((item) => (
                <tr key={item.equipment_id} className="border-b last:border-0 hover:bg-muted/30">
                  <td className="px-4 py-3">{item.name}</td>
                  <td className="px-4 py-3 font-mono text-xs">{item.equipment_id}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {EQUIPMENT_TYPE_LABELS[item.equipment_type] ?? item.equipment_type}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{item.production_line}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={item.status} />
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-muted">
                        <div
                          className={`h-full rounded-full ${
                            item.health_score >= 85
                              ? "bg-emerald-500"
                              : item.health_score >= 70
                                ? "bg-amber-500"
                                : "bg-red-500"
                          }`}
                          style={{ width: `${item.health_score}%` }}
                        />
                      </div>
                      <span className="tabular-nums text-xs text-muted-foreground">
                        {item.health_score}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      href={`/equipment/${item.equipment_id}`}
                      className="text-xs text-violet-600 hover:underline"
                    >
                      查看详情
                    </Link>
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
