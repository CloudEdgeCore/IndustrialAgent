"use client";

import Link from "next/link";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import { RiskBadge } from "@/components/ui-bits";
import { agentChatStream, api, type AgentEvent, type ReportDetail } from "@/lib/api";
import { clearToken, getToken, setToken, subscribeToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

type StepEvent = { label: string; status: string; tool?: string | null };

type Turn = {
  id: string;
  query: string;
  steps: StepEvent[];
  result?: AgentEvent;
  report?: ReportDetail | null;
  error?: string;
  running: boolean;
};

const TOOL_LABELS: Record<string, string> = {
  "sql.query": "业务数据查询",
  "sql.alarm_search": "报警信息查询",
  "sql.history_case": "历史维修记录",
  "timeseries.query": "设备运行数据",
  "analysis.run": "数据分析",
  "rag.search": "知识库检索",
  "report.generate": "报告生成",
};

const QUICK_PROMPTS: { label: string; query: string }[] = [
  { label: "分析设备故障", query: "3 号设备主轴温度连续超过 85℃，同时出现 E102 报警，帮我分析原因。" },
  { label: "分析质量异常", query: "最近 3 天 A 产品不良率为什么升高？" },
  { label: "查询报警代码", query: "E102 报警应该怎么处理？" },
  { label: "分析工艺参数", query: "分析昨天 2 号产线压力波动异常的原因。" },
  { label: "生成日报", query: "帮我生成一份今天的生产日报。" },
];

export default function AiDiagnosisPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const token = useSyncExternalStore(subscribeToken, getToken, () => null);
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin123");
  const [loginError, setLoginError] = useState<string | null>(null);
  const pendingQueryRef = useRef<string | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const bootstrappedRef = useRef(false);

  useEffect(() => {
    if (bootstrappedRef.current) return;
    bootstrappedRef.current = true;
    void (async () => {
      const preset = new URLSearchParams(window.location.search).get("q");
      if (!preset) return;
      setInput(preset);
      pendingQueryRef.current = preset;
      const existing = getToken();
      if (existing) await submit(preset, existing);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleLogin() {
    setLoginError(null);
    try {
      const response = await api.login(username, password);
      setToken(response.access_token);
      const pending = pendingQueryRef.current;
      pendingQueryRef.current = null;
      if (pending) void submit(pending, response.access_token);
    } catch {
      setLoginError("用户名或密码错误（演示账号 admin / admin123）");
    }
  }

  function handleLogout() {
    clearToken();
    setTurns([]);
    setActiveId(null);
  }

  async function submit(query: string, authToken?: string) {
    const currentToken = authToken ?? token;
    if (!query.trim() || !currentToken) return;
    const turnId = crypto.randomUUID();
    setTurns((prev) => [
      ...prev,
      { id: turnId, query, steps: [], running: true },
    ]);
    setActiveId(turnId);
    setInput("");

    const patch = (updater: (turn: Turn) => Turn) =>
      setTurns((prev) => prev.map((turn) => (turn.id === turnId ? updater(turn) : turn)));

    try {
      for await (const event of agentChatStream(
        {
          query,
          session_id: sessionIdRef.current ?? undefined,
          context: {},
        },
        currentToken,
      )) {
        if (event.type === "step") {
          patch((turn) => ({
            ...turn,
            steps: [
              ...turn.steps,
              { label: event.label ?? "", status: event.status ?? "done", tool: event.tool },
            ],
          }));
        } else if (event.type === "result") {
          if (event.session_id) sessionIdRef.current = event.session_id;
          patch((turn) => ({ ...turn, result: event, running: false }));
          if (event.report_id) {
            api
              .report(event.report_id)
              .then((report) => patch((turn) => ({ ...turn, report })))
              .catch(() => undefined);
          }
        } else if (event.type === "error") {
          patch((turn) => ({ ...turn, error: event.message ?? "未知错误", running: false }));
        } else if (event.type === "warning") {
          patch((turn) => ({
            ...turn,
            steps: [...turn.steps, { label: event.message ?? "警告", status: "error" }],
          }));
        }
      }
    } catch (err) {
      patch((turn) => ({ ...turn, error: String(err), running: false }));
    } finally {
      patch((turn) => ({ ...turn, running: false }));
    }
  }

  if (!token) {
    return (
      <div className="flex min-h-[70vh] items-center justify-center">
        <div className="w-full max-w-sm rounded-xl border bg-card p-6">
          <h1 className="text-lg font-semibold">登录 · Industrial Insight AI</h1>
          <p className="mt-1 text-xs text-muted-foreground">
            AI 诊断需要登录（演示账号 admin / admin123）
          </p>
          <div className="mt-4 space-y-3">
            <input
              className="w-full rounded-md border px-3 py-2 text-sm outline-none focus:border-violet-400"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="用户名"
            />
            <input
              type="password"
              className="w-full rounded-md border px-3 py-2 text-sm outline-none focus:border-violet-400"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="密码"
              onKeyDown={(event) => {
                if (event.key === "Enter") void handleLogin();
              }}
            />
            {loginError ? <p className="text-xs text-red-600">{loginError}</p> : null}
            <button
              onClick={() => void handleLogin()}
              className="w-full rounded-md bg-violet-600 py-2 text-sm font-medium text-white hover:bg-violet-500"
            >
              登录
            </button>
          </div>
        </div>
      </div>
    );
  }

  const active = turns.find((turn) => turn.id === activeId) ?? null;

  return (
    <div className="flex h-[calc(100vh-3.5rem-3rem)] gap-4">
      <aside className="flex w-64 shrink-0 flex-col rounded-xl border bg-card">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <span className="text-sm font-semibold">对话记录</span>
          <button onClick={handleLogout} className="text-xs text-muted-foreground hover:text-foreground">
            退出
          </button>
        </div>
        <div className="flex-1 space-y-1 overflow-y-auto p-2">
          {turns.length === 0 ? (
            <p className="px-2 py-4 text-xs text-muted-foreground">
              暂无对话，向右侧提问开始分析。
            </p>
          ) : (
            [...turns].reverse().map((turn) => (
              <button
                key={turn.id}
                onClick={() => setActiveId(turn.id)}
                className={cn(
                  "block w-full truncate rounded-md px-3 py-2 text-left text-xs",
                  turn.id === activeId
                    ? "bg-violet-50 text-violet-700"
                    : "text-muted-foreground hover:bg-muted",
                )}
              >
                {turn.query}
              </button>
            ))
          )}
        </div>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col rounded-xl border bg-card">
        <div className="flex-1 space-y-5 overflow-y-auto p-6">
          {!active ? (
            <div className="mx-auto max-w-xl pt-16 text-center">
              <div className="text-lg font-semibold">AI 诊断工作台</div>
              <p className="mt-2 text-sm text-muted-foreground">
                询问设备、工艺或质量问题，例如：
                <br />
                “分析 3 号设备过去 2 小时温度异常原因”
              </p>
              <div className="mt-6 flex flex-wrap justify-center gap-2">
                {QUICK_PROMPTS.map((prompt) => (
                  <button
                    key={prompt.label}
                    onClick={() => void submit(prompt.query)}
                    className="rounded-full border px-3 py-1.5 text-xs hover:border-violet-300 hover:bg-violet-50 hover:text-violet-700"
                  >
                    {prompt.label}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <>
              <div className="flex justify-end">
                <div className="max-w-[80%] rounded-xl rounded-br-sm bg-violet-600 px-4 py-2.5 text-sm text-white">
                  {active.query}
                </div>
              </div>

              <div className="space-y-3">
                <div className="flex items-center gap-2 text-sm font-medium">
                  {active.running ? (
                    <span className="inline-block size-2 animate-pulse rounded-full bg-violet-500" />
                  ) : (
                    <span className="inline-block size-2 rounded-full bg-emerald-500" />
                  )}
                  分析任务
                </div>
                <ul className="space-y-2 border-l-2 border-muted pl-4">
                  {active.steps.map((step, index) => (
                    <li key={index} className="flex items-center gap-2 text-sm">
                      {step.status === "error" ? (
                        <span className="text-red-500">✕</span>
                      ) : (
                        <span className="text-emerald-600">✓</span>
                      )}
                      <span>{step.label}</span>
                      {step.tool ? (
                        <span className="text-xs text-muted-foreground">
                          （{TOOL_LABELS[step.tool] ?? step.tool}）
                        </span>
                      ) : null}
                    </li>
                  ))}
                  {active.running ? (
                    <li className="flex items-center gap-2 text-sm text-muted-foreground">
                      <span className="inline-block size-3 animate-spin rounded-full border-2 border-violet-400 border-t-transparent" />
                      正在执行…
                    </li>
                  ) : null}
                </ul>
              </div>

              {active.result?.tool_results?.length ? (
                <div className="rounded-xl border border-dashed bg-muted/20 p-4">
                  <div className="text-sm font-semibold">证据</div>
                  <div className="mt-3 grid gap-2 sm:grid-cols-2">
                    {active.result.tool_results.map((item, index) => (
                      <div key={index} className="rounded-lg border bg-card px-3 py-2">
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-medium">
                            {TOOL_LABELS[item.tool] ?? item.tool}
                          </span>
                          <span
                            className={cn(
                              "rounded-full px-1.5 py-0.5",
                              item.status === "done"
                                ? "bg-emerald-50 text-emerald-600"
                                : "bg-red-50 text-red-600",
                            )}
                          >
                            {item.status === "done" ? "成功" : "失败"}
                          </span>
                        </div>
                        <div className="mt-1 truncate text-xs text-muted-foreground">
                          来源：{item.source ?? "-"}
                          {item.row_count != null ? ` · ${item.row_count} 行` : ""}
                        </div>
                      </div>
                    ))}
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">
                    共 {active.result.evidence_count ?? 0} 条证据，关键结论均可追溯至上述数据来源。
                  </p>
                </div>
              ) : null}

              {active.report ? (
                <div className="rounded-xl border bg-card p-5">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold">诊断结果</span>
                      <RiskBadge level={active.report.risk_level} />
                    </div>
                    <Link
                      href={`/reports/${active.report.report_id}`}
                      className="rounded-md bg-violet-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-500"
                    >
                      生成报告 #{active.report.report_id}
                    </Link>
                  </div>
                  <p className="mt-3 text-sm leading-6">{active.result?.final_answer}</p>
                </div>
              ) : active.result ? (
                <div className="rounded-xl border bg-card p-5">
                  <span className="text-sm font-semibold">诊断结果</span>
                  <p className="mt-3 text-sm leading-6">{active.result.final_answer}</p>
                </div>
              ) : null}

              {active.error ? (
                <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
                  执行失败：{active.error}
                </div>
              ) : null}
            </>
          )}
        </div>

        <div className="border-t p-4">
          <div className="flex gap-3">
            <input
              className="flex-1 rounded-lg border px-4 py-2.5 text-sm outline-none focus:border-violet-400"
              placeholder="询问设备、工艺或质量问题，例如：“分析 3 号设备过去 2 小时温度异常原因”"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void submit(input);
                }
              }}
              disabled={active?.running}
            />
            <button
              onClick={() => void submit(input)}
              disabled={!input.trim() || active?.running}
              className="rounded-lg bg-violet-600 px-5 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-40"
            >
              分析
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
