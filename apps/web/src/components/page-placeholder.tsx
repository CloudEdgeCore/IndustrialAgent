import type { ReactNode } from "react";

export function PagePlaceholder({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      </div>
      <div className="rounded-xl border border-dashed bg-card p-10 text-center text-sm text-muted-foreground">
        {children ?? "页面骨架已就绪，将在 P5 Web 层实现。"}
      </div>
    </div>
  );
}
