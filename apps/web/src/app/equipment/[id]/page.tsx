import { PagePlaceholder } from "@/components/page-placeholder";

export default async function EquipmentDetailPage({
  params,
}: PageProps<"/equipment/[id]">) {
  const { id } = await params;
  return (
    <PagePlaceholder
      title="设备详情"
      description="实时监控、趋势分析、告警、维修记录与 AI 诊断入口。"
    >
      <p className="text-sm text-muted-foreground">
        设备编号：
        <span className="font-medium text-foreground">{id}</span>
      </p>
    </PagePlaceholder>
  );
}
