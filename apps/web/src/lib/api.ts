/** 类型化 API 客户端（经 Nginx / Next rewrite 的 /api 前缀）。 */

export type Equipment = {
  equipment_id: string;
  name: string;
  equipment_type: string;
  model: string | null;
  production_line: string;
  status: string;
  health_score: number;
};

export type Alarm = {
  alarm_code: string;
  equipment_id: string;
  equipment_name?: string | null;
  severity: string;
  status: string;
  occurred_at: string;
  cleared_at: string | null;
  description: string | null;
};

export type EquipmentDetail = Equipment & {
  active_alarms: Alarm[];
  latest_readings: Record<string, number>;
  latest_reading_at?: string | null;
  data_as_of?: string | null;
  data_lag_hours?: number | null;
};

export type SensorPoint = { timestamp: string; value: number; quality: string };

export type MaintenanceRecord = {
  id: number;
  equipment_id: string;
  maintenance_type: string;
  description: string;
  root_cause: string | null;
  actions: string | null;
  technician: string | null;
  related_alarm_code: string | null;
  occurred_at: string;
  completed_at: string | null;
};

export type QualitySummary = {
  product_id: string;
  days: number;
  total: number;
  pass_count: number;
  fail_count: number;
  fail_rate: number;
  baseline_fail_rate: number | null;
  top_defects: { defect_type: string; count: number }[];
  by_equipment: { equipment_id: string; count: number }[];
  /** 窗口锚点（相对时间的"现在"）与数据滞后，用于界面标注"数据截至" */
  data_as_of?: string | null;
  data_lag_hours?: number | null;
  anchor_source?: string | null;
};

export type Freshness = {
  anchor: string;
  resolved_from: "data" | "now";
  lag_hours: number;
  domains: Record<string, string | null>;
};

export type QualityTrendPoint = {
  date: string;
  total: number;
  fail_count: number;
  fail_rate: number;
};

export type DocumentInfo = {
  document_id: number;
  title: string;
  document_type: string;
  equipment_type: string | null;
  version: string | null;
  status: string;
  chunk_count: number;
};

export type SearchHit = {
  document_title: string;
  document_type: string;
  version: string | null;
  chunk_index: number;
  section: string | null;
  content: string;
  scores: Record<string, number | null>;
};

export type ReportInfo = {
  report_id: number;
  report_type: string;
  title: string;
  equipment_id: string | null;
  risk_level: string | null;
  status: string;
  created_at: string;
};

export type ReportDetail = ReportInfo & { content_markdown: string | null };

export type Grounding = {
  checked: number;
  matched: number;
  unmatched: string[];
  ratio: number;
  degraded_agents?: string[];
};

export type AgentEvent = {
  type: "step" | "result" | "error" | "warning";
  label?: string;
  status?: string;
  tool?: string | null;
  detail?: string | null;
  session_id?: string;
  task_type?: string;
  agents?: string[];
  final_answer?: string;
  report_id?: number | null;
  tool_results?: {
    tool: string;
    status: string;
    source: string | null;
    row_count: number | null;
  }[];
  evidence_count?: number;
  grounding?: Grounding;
  message?: string;
};

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

function qs(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

async function getJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, init);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`请求失败 ${response.status}: ${text.slice(0, 200)}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  freshness: () => getJSON<Freshness>("/api/meta/freshness"),
  equipmentList: (params: { status?: string; equipment_type?: string; limit?: number } = {}) =>
    getJSON<{ total: number; items: Equipment[] }>(`/api/equipment${qs({ ...params, limit: params.limit ?? 200 })}`),
  equipmentDetail: (id: string) => getJSON<EquipmentDetail>(`/api/equipment/${id}`),
  equipmentReadings: (id: string, sensorType: string, hours = 24, bucket = "5m") =>
    getJSON<SensorPoint[]>(`/api/equipment/${id}/readings${qs({ sensor_type: sensorType, hours, bucket })}`),
  equipmentMaintenance: (id: string) =>
    getJSON<MaintenanceRecord[]>(`/api/equipment/${id}/maintenance`),
  alarms: (params: { status?: string; equipment_id?: string; limit?: number } = {}) =>
    getJSON<Alarm[]>(`/api/alarms${qs({ ...params, limit: params.limit ?? 50 })}`),
  qualitySummary: (productId = "PRD-A", days = 3) =>
    getJSON<QualitySummary>(`/api/quality/summary${qs({ product_id: productId, days })}`),
  qualityTrend: (productId = "PRD-A", days = 14) =>
    getJSON<QualityTrendPoint[]>(`/api/quality/trend${qs({ product_id: productId, days })}`),
  documents: () => getJSON<DocumentInfo[]>("/api/knowledge/documents"),
  searchKnowledge: (query: string, topK = 5, documentType?: string) =>
    getJSON<SearchHit[]>("/api/knowledge/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, top_k: topK, document_type: documentType }),
    }),
  reports: (limit = 20) => getJSON<{ total: number; items: ReportInfo[] }>(`/api/reports${qs({ limit })}`),
  report: (id: number) => getJSON<ReportDetail>(`/api/reports/${id}`),
  login: (username: string, password: string) =>
    getJSON<{ access_token: string; user: { username: string; display_name: string | null } }>(
      "/api/auth/login",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      },
    ),
  sessionMessages: (sessionId: string, token: string) =>
    getJSON<{ id: number; role: string; content: string | null }[]>(
      `/api/agent/sessions/${sessionId}/messages`,
      { headers: { Authorization: `Bearer ${token}` } },
    ),
};

/** Agent SSE 流（POST，逐事件解析）。 */
export async function* agentChatStream(
  payload: { query: string; session_id?: string; context?: Record<string, unknown> },
  token: string,
): AsyncGenerator<AgentEvent> {
  const response = await fetch(`${BASE}/api/agent/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok || !response.body) {
    const text = await response.text().catch(() => "");
    throw new Error(`Agent 请求失败 ${response.status}: ${text.slice(0, 200)}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const line = chunk.split("\n").find((item) => item.startsWith("data: "));
      if (line) yield JSON.parse(line.slice(6)) as AgentEvent;
    }
  }
}
