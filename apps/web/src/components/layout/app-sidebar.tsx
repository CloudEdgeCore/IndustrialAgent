"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BarChart3,
  BookOpen,
  Bot,
  Factory,
  FileText,
  LayoutDashboard,
  Settings,
  SlidersHorizontal,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";

const NAV_ITEMS: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/overview", label: "Overview", icon: LayoutDashboard },
  { href: "/ai", label: "AI 诊断", icon: Bot },
  { href: "/equipment", label: "设备中心", icon: Factory },
  { href: "/process", label: "工艺分析", icon: SlidersHorizontal },
  { href: "/quality", label: "质量分析", icon: BarChart3 },
  { href: "/knowledge", label: "知识库", icon: BookOpen },
  { href: "/reports", label: "报告中心", icon: FileText },
  { href: "/settings", label: "系统设置", icon: Settings },
];

export function AppSidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r bg-sidebar">
      <div className="flex h-14 items-center gap-2 border-b px-4">
        <Activity className="size-5 text-primary" />
        <span className="text-sm font-semibold tracking-tight">
          Industrial Insight AI
        </span>
      </div>
      <nav className="flex-1 space-y-1 p-3">
        {NAV_ITEMS.map((item) => {
          const active =
            pathname === item.href || pathname.startsWith(`${item.href}/`);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-sidebar-accent font-medium text-foreground"
                  : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
              )}
            >
              <Icon className="size-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="border-t px-4 py-3 text-xs text-muted-foreground">
        P0 骨架 · v0.1.0
      </div>
    </aside>
  );
}
