import { Bell } from "lucide-react";

import { DataFreshnessBar } from "@/components/layout/data-freshness";
import { Button } from "@/components/ui/button";

export function TopBar() {
  return (
    <header className="flex h-14 items-center justify-between border-b bg-background px-6">
      <div className="flex items-center gap-3 text-sm text-muted-foreground">
        <span>Plant A · 演示工厂（模拟数据）</span>
        <DataFreshnessBar />
      </div>
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" aria-label="告警通知">
          <Bell />
        </Button>
        <div className="flex size-8 items-center justify-center rounded-full bg-muted text-xs font-medium">
          AI
        </div>
      </div>
    </header>
  );
}
