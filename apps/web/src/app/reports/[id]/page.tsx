import { PagePlaceholder } from "@/components/page-placeholder";

export default async function ReportDetailPage({
  params,
}: PageProps<"/reports/[id]">) {
  const { id } = await params;
  return (
    <PagePlaceholder
      title="报告详情"
      description="问题概述、数据范围、证据链、根因候选与建议。"
    >
      <p className="text-sm text-muted-foreground">
        报告编号：
        <span className="font-medium text-foreground">{id}</span>
      </p>
    </PagePlaceholder>
  );
}
