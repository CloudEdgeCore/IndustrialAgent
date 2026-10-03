# Industrial Agent

**基于大模型 Agent 的工业设备故障诊断与质量分析系统**

[![CI](https://github.com/CloudEdgeCore/IndustrialAgent/actions/workflows/ci.yml/badge.svg)](https://github.com/CloudEdgeCore/IndustrialAgent/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-%E2%89%A53.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=nextdotjs&logoColor=white)](https://nextjs.org/)
[![LangGraph](https://img.shields.io/badge/Agent-LangGraph-FF6F61)](https://github.com/langchain-ai/langgraph)

Industrial Agent 面向制造企业的**设备、工艺、质量**场景，将设备运行时序数据、工艺参数、质量检测数据与工业知识库统一接入多 Agent 协作平台，通过 LangGraph 编排与 Tool Calling 提供设备故障诊断、工艺异常分析、质量问题溯源与自动报告生成能力，并保证每条结论**有数值、有来源、可追溯**。

## 目录

- [1. 核心特性](#1-核心特性)
- [2. 系统架构](#2-系统架构)
- [3. 技术栈](#3-技术栈)
- [4. 目录结构](#4-目录结构)
- [5. 快速开始](#5-快速开始)
- [6. 使用指南](#6-使用指南)
- [7. API 概览](#7-api-概览)
- [8. Agent 与工具层](#8-agent-与工具层)
- [9. 测试与质量保障](#9-测试与质量保障)
- [10. 项目状态](#10-项目状态)
- [11. 文档索引](#11-文档索引)
- [12. 贡献与许可](#12-贡献与许可)

## 1. 核心特性

| 能力 | 说明 |
|---|---|
| 设备故障诊断 | 结合实时/历史时序、报警事件、维修案例与知识库，输出根因候选、排查顺序与风险等级 |
| 工艺异常分析 | 工艺参数相关性 / 趋势 / 异常窗口分析（示例：LINE-2 压力波动与阀门开度相关系数 0.93） |
| 质量问题溯源 | 不良率趋势、缺陷 Pareto、设备与班次分布、根因定位（示例：PRD-A 近 3 天不良率 3.5% vs 基线 1.8%，定位至 EQ-003 / surface_crack） |
| 工业知识问答 | 向量 + 关键词混合检索（RRF + Rerank），回答携带 文档 / 章节 / 版本 引用 |
| 自动报告生成 | Evidence-based 结构化报告落库，支持 Markdown 导出与打印 PDF |
| 数值证据校验 | 结论中的测量值与工具返回 payload 做容差比对，产出"可溯源比例 + 未溯源清单"（见 §8.3） |
| 数据新鲜度可见 | 分析窗口锚定数据末尾，界面明确标注"数据截至 + 滞后"（见 §5.7） |
| 多轮会话 | 会话历史注入 Router 与专业 Agent 提示词，支持追问 |
| 全链路可观测 | Langfuse 追踪（可选接入）、工具调用审计日志（含越权尝试）、SSE 执行步骤可视化 |

设计原则：

- **Evidence-based**：问题描述、数据范围、异常发现、根因候选、证据、排查顺序、风险、来源，缺一不可（架构红线）；并由**数值 grounding 校验**把"禁止编造数值"从提示词约束变成可量化信号。
- **Tool-first**：Agent 不直接访问数据库，一律经工具层（Registry → 权限校验 → Executor）；禁止 LLM 生成任意 SQL。
- **LLM 可替换**：统一 OpenAI-compatible 接口，默认 Qwen DashScope 兼容模式，可切换任意兼容端点。

## 2. 系统架构

```text
┌──────────────────────────────────────────────────────────────────┐
│  Web（Next.js 16 + shadcn/ui + ECharts）                          │
│  总览 · AI 诊断(SSE) · 设备中心 · 质量分析 · 知识库 · 报告中心      │
└───────────────────────────────┬──────────────────────────────────┘
                                │ REST / SSE
┌───────────────────────────────▼──────────────────────────────────┐
│  Nginx :80（/api → FastAPI；/ → Web；支持 SSE 长连接）             │
└───────────────────────────────┬──────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────┐
│  FastAPI :8000                                                   │
│  REST API · SSE · JWT 鉴权（Redis 会话，可降级）                   │
│                                                                  │
│  Agent Orchestrator（LangGraph）                                  │
│  Router ──▶ Equipment / Process / Quality ──▶ Report             │
│                    │ Tool Calling                                │
│  Tool Layer：SQL · TimeSeries · RAG · Analysis · Alarm/Case · 报告 │
└───────┬──────────────────────┬───────────────────────┬───────────┘
        │                      │                       │
┌───────▼────────┐     ┌───────▼───────┐       ┌───────▼───────┐
│ PostgreSQL 17  │     │ Redis 7       │       │ MinIO         │
│ TimescaleDB    │     │ 会话 / 缓存    │       │ 对象存储       │
│ pgvector       │     └───────────────┘       └───────────────┘
└────────────────┘
```

### 安全边界（架构红线）

1. **Agent 数量锁定**：1 Router + 4 专业 Agent（Equipment / Process / Quality / Report），不新增；
2. **SQL 全链路受控**：Query Planner → 结构化 Query → SQL Builder → Validator → 只读账号 `tool_ro`（双层防线）。Validator 在 `run_readonly_query` 内**强制调用**，`allowed_tables` 为必填参数，任何新查询路径（含 RAG 检索）都无法绕过；
3. **权限矩阵**：每个 Agent 只能调用白名单内的工具，越权调用被拦截并写入审计日志（未知工具、权限拒绝、参数非法、执行异常、成功五种结果全部留痕）；
4. **Analysis 白名单执行**：仅允许预定义统计算子（相关性 / z-score / IQR / 趋势 / Isolation Forest / Pareto 等），禁止执行任意系统代码。

### 数据窗口锚点（为什么不是 `datetime.now()`）

模拟/回放数据集的时间轴末尾固定在生成时刻。若相对时间窗口锚定真实时钟，数据落库数天后
"最近 24 小时 / 最近 3 天" 会滑出数据集：图表变空、不良率场景退化为基线、测试静默失败。

因此 `tools/freshness.py` 提供统一**窗口锚点**：

| `WINDOW_ANCHOR` | 行为 | 适用 |
|---|---|---|
| `data`（默认） | 窗口锚定"数据最新时间" | 模拟 / 回放数据集、Demo、CI |
| `now` | 窗口锚定真实时钟 | 接入实时数据流的生产环境（滞后由 `/api/meta/freshness` 暴露） |

窗口锚点同时写入工具返回的 `meta.window`（anchor / anchor_source / data_lag_hours），
因此"最近 24 小时"这类相对窗口始终可还原为绝对时间区间。

## 3. 技术栈

| 模块 | 技术 | 版本 |
|---|---|---|
| Web | Next.js + TypeScript | Next 16.3 / React 19 / TS 5.9 |
| UI / 图表 | shadcn/ui + Tailwind CSS + Apache ECharts | Tailwind 4 / ECharts 6 |
| 后端 | FastAPI + SQLAlchemy + Pydantic + Alembic | Python ≥ 3.12 |
| Agent | LangGraph + LangChain | ≥ 0.2 / ≥ 0.3 |
| LLM | OpenAI-compatible（默认 Qwen DashScope） | 可替换 |
| 数据库 | PostgreSQL 17 + TimescaleDB + pgvector | timescaledb-ha:pg17 |
| 缓存 / 会话 | Redis | 7 |
| 对象存储 | MinIO | latest |
| 可观测性 | Langfuse（可选） | ≥ 3.0 |
| 部署 | Docker Compose + Nginx | — |
| 测试 / CI | pytest + ruff + GitHub Actions + pnpm | — |

## 4. 目录结构

```text
industrial-agent/
├── apps/
│   ├── api/                        # FastAPI 后端（REST + SSE + JWT）
│   └── web/                        # Next.js 前端（shadcn/ui + ECharts）
├── agent/                          # LangGraph 编排
│   ├── router/                     #   意图路由
│   ├── equipment/  process/        #   设备 / 工艺 Agent
│   ├── quality/    report/         #   质量 / 报告 Agent
│   ├── grounding.py                #   结论数值 grounding 校验
│   ├── history.py                  #   多轮会话历史渲染
│   └── runner.py                   #   运行入口 run_agent()
├── tools/                          # 工具层（Registry + 权限 + 审计）
│   ├── sql/  timeseries/           #   结构化查询 / 时序查询
│   ├── rag/  analysis/  reports/   #   混合检索 / 白名单统计 / 报告生成
│   ├── freshness.py                #   数据新鲜度与窗口锚点
│   └── loader.py                   #   工具注册与加载
├── models/                         # SQLAlchemy 数据模型（15 张表）
├── data/
│   ├── simulator/                  # 可复现数据模拟器（固定种子）
│   └── fixtures/                   # 设备/报警/缺陷/产线目录 + 场景清单
├── tests/
│   ├── evals/                      # Agent 评测（42 条工业问题 + report.json 证据）
│   └── integration/                # 数据库 / 接口集成测试
├── docker/                         # Dockerfile / nginx / initdb
├── docs/                           # PRD / 架构 / 选型 / 页面设计 / DEMO
├── docker-compose.yml
├── CLAUDE.md                       # 项目执行守则（防偏移红线）
└── 05-开发计划.md                  # 阶段计划与出口条件（进度基准）
```

## 5. 快速开始

### 5.1 前置要求

- Docker Engine + Compose v2（推荐方式）
- 本地开发另需：Python ≥ 3.12、Node.js ≥ 22、pnpm 11
- 可选：OpenAI-compatible LLM API Key（未配置时 Agent 走本地降级路径，界面与测试仍可用）

### 5.2 一键启动（Docker Compose）

```bash
git clone https://github.com/CloudEdgeCore/IndustrialAgent.git
cd IndustrialAgent
cp .env.example .env        # Windows: copy .env.example .env
docker compose up -d        # 启动全部服务（6 个容器）
```

| 入口 | 地址 |
|---|---|
| Web 界面 | http://localhost |
| API 文档（Swagger，经 Nginx） | http://localhost/api/docs |
| 后端直连文档 | http://localhost:8000/docs |
| MinIO 控制台 | http://localhost:9001 |

首次启动后初始化数据库与演示数据（容器内执行，无需本地 Python 环境）：

```bash
docker compose exec backend alembic -c apps/api/alembic.ini upgrade head  # 建表 + hypertable + 只读账号
docker compose exec backend python -m data.simulator                      # 模拟数据（seed=42，含场景注入）
docker compose exec backend python -m tools.rag ingest                    # 导入知识库（6 篇文档 → 22 分块）
```

> 配置真实 LLM：在 `.env` 中填入 `LLM_API_KEY`（默认 Qwen DashScope 兼容模式），重启 backend 容器生效。

### 5.3 本地开发

后端：

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"      # Windows；macOS/Linux 用 source .venv/bin/activate
alembic -c apps/api/alembic.ini upgrade head
python -m data.simulator
cd apps/api && uvicorn app.main:app --reload         # http://localhost:8000/docs
```

前端：

```bash
cd apps/web
pnpm install
pnpm dev        # http://localhost:3000（端口占用时：pnpm dev --port 3001）
```

### 5.4 端口约定

| 服务 | 宿主机端口 | 说明 |
|---|---|---|
| Nginx | 80 | Web + `/api` 统一入口 |
| 后端（FastAPI） | 8000 | 可直连调试 |
| 前端直连 | 13000 | 容器映射（容器内 3000） |
| PostgreSQL | 5432 | TimescaleDB + pgvector |
| Redis | 16379 | 容器内 6379，避开本机其他项目占用 |
| MinIO | 9000 / 9001 | API / 控制台 |

### 5.5 环境变量（`.env`）

| 变量 | 说明 | 默认值 |
|---|---|---|
| `DATABASE_URL` | 业务库连接（psycopg3） | `postgresql+psycopg://industrial:industrial@localhost:5432/industrial_agent` |
| `TOOL_DATABASE_URL` | 工具层只读账号（仅 SELECT） | `tool_ro:tool_ro@...` |
| `REDIS_URL` | 会话与缓存 | `redis://localhost:16379/0` |
| `WINDOW_ANCHOR` | 相对时间窗口锚点：`data`（数据末尾）/ `now`（真实时钟） | `data` |
| `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY` | OpenAI-compatible LLM 配置 | DashScope / `qwen-plus` |
| `JWT_SECRET` / `JWT_EXPIRE_MINUTES` | 鉴权配置（生产必改） | `dev-secret-change-me` / 720 |
| `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` / `MINIO_ENDPOINT` | 对象存储 | minioadmin |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`（可选） | LLM 全链路追踪；未配置零开销跳过 | — |
| `EMBEDDING_*`（可选） | 外部 Embedding；未配置使用确定性特征哈希实现（**词法级，非语义向量**） | `bge-m3` / 1024 维 |

### 5.6 模拟数据说明

- 30 台设备（CNC / 注塑机 / 装配线）× 3 条产线、9 类报警、6 类缺陷字典；
- 固定随机种子（`--seed 42`），同种子 + 锚点完全可复现；场景清单输出至 `data/fixtures/manifest.json`；
- 内置演示场景：EQ-003 主轴超温（E102，连续 24 分钟 > 85℃、冷却液流量 -18%）· EQ-024 停机 6h · LINE-2 压力波动 · PRD-A 近 3 天不良率 1.8% → **3.5%**（EQ-003 单台升至 15%，surface_crack 占该台缺陷 70%）；
- 快速档（CI / 低配机器）：`python -m data.simulator --days 2 --quality-days 5 --history-days 10`。

## 6. 使用指南

### 6.1 演示账号

| 用户名 | 密码 | 说明 |
|---|---|---|
| `admin` | `admin123` | 演示管理员，Agent 端点需登录（JWT） |

### 6.2 页面导览

| 页面 | 路径 | 说明 |
|---|---|---|
| 总览 | `/overview` | KPI、AI 风险摘要（一键跳转分析）、设备健康、不良率趋势、活跃报警、最近分析 |
| AI 诊断 | `/ai` | SSE 流式执行步骤 + Evidence 证据区 + 结果卡 / 报告联动 |
| 设备中心 | `/equipment` | 列表（筛选 / 健康度）→ 详情（监控卡片、趋势图、告警、维修记录、AI 入口） |
| 质量分析 | `/quality` | 不良率趋势、缺陷 Pareto、不良设备分布、AI 洞察 |
| 知识库 | `/knowledge` | RAG 混合检索（带引用来源）+ 文档管理 |
| 报告中心 | `/reports` | 列表 / 详情 / Markdown 导出 / 打印 PDF |

> 规划中页面（当前为占位）：工艺分析 `/process`、质量追溯 `/quality/trace`、系统设置 `/settings`。
> 界面截图将补充至 `docs/screenshots/`。

### 6.3 AI 诊断流程示例

1. 打开 http://localhost/ai 并登录，输入：`分析 EQ-003 主轴温度异常`；
2. 页面实时呈现执行步骤（SSE）与 Evidence 证据区（工具 / 来源 / 行数）；
3. 结论卡包含风险等级、根因候选与置信度、排查顺序；点击「生成报告」落库；
4. 在报告详情页导出 Markdown 或打印 PDF。

SSE 事件流示例：

```text
data: {"type":"step","label":"已识别：设备故障诊断","status":"done"}
data: {"type":"step","label":"查询设备运行数据","status":"done"}
...
data: {"type":"result","final_answer":"…","report_id":12}
```

### 6.4 演示剧本

完整演示（PRD 场景 A~D，约 10 分钟）：见 [`docs/DEMO.md`](docs/DEMO.md)。

## 7. API 概览

经 Nginx（`/api/` 前缀）或后端直连（`http://localhost:8000`）访问：

| 方法 | 路径 | 说明 | 鉴权 |
|---|---|---|---|
| GET | `/health` | 健康检查 | 否 |
| GET | `/meta/freshness` | 数据新鲜度：窗口锚点 / 锚点来源 / 滞后小时数 / 各领域最新时间 | 否 |
| POST | `/auth/login` | 登录 → JWT | 否 |
| POST | `/auth/logout` | 登出（Redis 会话吊销，可降级） | 是 |
| GET | `/auth/me` | 当前用户 | 是 |
| GET | `/equipment` | 设备列表（筛选 / 健康度） | 否 |
| GET | `/equipment/{id}` | 设备详情（活跃报警 + 最新读数） | 否 |
| GET | `/equipment/{id}/readings` | 时序读数 | 否 |
| GET | `/equipment/{id}/maintenance` | 维修记录 | 否 |
| GET | `/alarms` | 报警列表 | 否 |
| GET | `/quality/trend` | 不良率趋势 | 否 |
| GET | `/quality/summary` | 质量汇总（Pareto / 设备分布） | 否 |
| GET | `/quality/inspections` | 质检明细 | 否 |
| GET | `/knowledge/documents` | 知识库文档列表 | 否 |
| POST | `/knowledge/search` | 混合检索（带引用） | 否 |
| GET | `/reports` · `/reports/{id}` | 报告列表 / 详情 | 否 |
| GET | `/reports/{id}/export` | 报告 Markdown 导出 | 否 |
| POST | `/agent/chat`（SSE） | Agent 流式对话（步骤事件 → 结果事件） | 是 |
| GET | `/agent/sessions/{id}/messages` | 会话消息 | 是 |

## 8. Agent 与工具层

### 8.1 编排流程

```text
用户问题 → Router（意图路由：设备诊断 / 工艺分析 / 质量溯源 / 知识问答）
         → Equipment / Process / Quality（工具循环 → Evidence-based 结论）
         → Report（结论合并 → 结构化报告落库）
```

### 8.2 工具清单（7 个）

| 工具 | 说明 |
|---|---|
| `sql.query` | 结构化白名单查询（Planner → Builder → Validator → 只读库） |
| `sql.alarm_search` | 报警代码解释 / 报警事件检索 |
| `sql.history_case` | 历史维修案例检索 |
| `timeseries.query` | 时序 series / stats / anomaly_windows（TimescaleDB） |
| `analysis.run` | 白名单统计（相关性 / z-score / IQR / 趋势 / Isolation Forest / Pareto） |
| `rag.search` | 知识库混合检索（向量 + 关键词 RRF + Rerank，带引用元数据） |
| `report.generate` | Evidence-based 报告生成与落库 |

所有工具统一经 **Registry → 权限矩阵 → 审计日志** 执行。

审计记录覆盖 **not_found / denied / invalid / error / ok** 五种结果 —— 越权尝试同样留痕，
便于安全分析。日志以 JSON Lines 输出到 stdout（Docker 直接采集）：

```json
{"event":"tool_call","agent":"report","tool":"timeseries.query","status":"denied",
 "error":"agent 'report' 无权调用工具 'timeseries.query'"}
```

### 8.3 数值 grounding 校验（把红线变成机制）

Evidence 契约（字段齐备）由 Pydantic 保证，但"禁止编造数值"原先只是提示词约束 ——
幻觉数值同样能通过 schema。`agent/grounding.py` 把结论中的数值与工具真实 payload 做比对：

| 规则 | 说明 |
|---|---|
| 计入校验 | 带小数点的数值，或 ≥10 且**不带**时长/计数单位的整数 |
| 不计入 | 时长与计数（`连续 24 分钟`、`最近 3 天`、`1 号产线`）、用户问题中已给出的数值 |
| 容差 | 相对 1% 或绝对 0.05（结论常做四舍五入：payload `92.17` → 结论 `92.2`） |
| 判定 | 样本 ≥3 且可溯源比例 <80% 时发出 `warning` 步骤事件；未溯源数值写入报告与界面 |

SSE `result` 事件附带汇总：`grounding.checked / matched / unmatched / degraded_agents`。
结论解析失败时不再伪装成正常结论，而是显式标记 `degraded` 并进入报告 findings。

## 9. 测试与质量保障

### 9.1 自动化测试

```bash
pytest                                  # 后端：257 项（其中 60 项为数据库集成测试，无库时自动跳过）
ruff check .                            # 后端 lint：0 错误
cd apps/web && pnpm lint && pnpm build  # 前端检查与构建
```

集成测试不依赖执行顺序：会话级 fixture 会确保知识库已导入（无库时静默跳过）。

### 9.2 Agent Eval

```bash
python tests/evals/runner.py                     # 离线模式（无需 Key，CI 用）
python tests/evals/runner.py --llm --workers 6   # 真实 LLM 全量（42 条，6 并发）
python tests/evals/runner.py --rescore           # 不重跑，按当前口径重新聚合
pytest tests/evals                               # pytest 入口（离线部分）
```

**指标口径**（完整定义见 `tests/evals/runner.py` 顶部与 `report.json.metric_definitions`）：

| 指标 | 定义 | 为什么这样定义 |
|---|---|---|
| `intent_acc` | LLM Router 产出的 task_type 与期望一致 | **产品指标** |
| `heuristic_intent_acc` | 关键词降级路由准确率 | 只代表兜底路径，**不代表 Agent 能力** |
| `tool_selection_rate` | 期望工具集合被**完整覆盖**的用例占比（按用例，不按调用次数） | "调用了很多工具且都没报错"不应得分 |
| `tool_recall` / `tool_calls_per_case` | 期望工具召回率 / 平均调用次数 | 召回率 + 效率信号 |
| `tool_call_success_rate` | 工具调用未报错比例 | 稳定性，**不代表选对工具** |
| `citation_answer_rate` | 需要知识库支撑的用例中，真的检索过知识库**且**关键词进入回答 | 端到端引用；只测检索器会变成自证 |
| `citation_retriever_rate` | 检索器 top-k 命中关键词 | 检索器诊断指标 |

**实测结果**（42 条测试集，真实 Qwen，6 并发；`report.json` 已随仓库提交，可逐用例复核）：

| 指标 | 全量（42 条） | 排除基础设施失败（31 条） | 基线 |
|---|---|---|---|
| 意图路由（LLM） | 73.8% (31/42) | **100% (31/31)** | ≥ 90% |
| 工具选择（严格） | 73.8% (31/42) | **100% (31/31)** | ≥ 95% |
| 引用（端到端） | 71.4% (10/14) | **100% (10/10)** | ≥ 90% |
| 工具调用成功率 | 97.5% (463/475) | — | ≥ 95% |
| 平均工具调用次数 | 11.3 次/用例 | — | 观测项 |
| 引用（检索器诊断） | 100% (22/22) | — | — |
| 意图路由（启发式兜底） | 92.9% (39/42) | — | 参考 |

> **为什么有两列**：本轮 42 条中有 **11 条因本机 HTTP 代理网络超时（`OpenAITimeoutError`）
> 未能执行**。这些用例被保守地计为"未命中"（全量列），同时单独统计并剔除后给出有效用例列
> —— 逐用例明细见 `report.json.details`，每条失败都带 `error` 字段。
> **两个口径都披露，基线判定使用有效用例口径**：只报前者会低估系统能力，只报后者会掩盖失败率。
>
> 网络失败数在多次运行间波动（实测 8~11 条），且全部来自同一类代理超时；
> **有效用例口径在三次独立全量运行中稳定为 97%~100% / 100% / 100%**。

离线模式（`pytest tests/evals`，CI 用，**不执行 Agent**）：启发式兜底路由 92.9% (39/42) ·
工具参数可用性 100% (39/39) · 检索器命中 100% (22/22)。

> 离线模式只验证兜底路由、工具参数兼容性与检索器，**不能作为 Agent 质量证据** ——
> 离线报告的 `measures_agent_behavior` 恒为 `false`（有测试锁定该语义）。
>
> 两种模式的报告分开落盘，避免互相覆盖：`tests/evals/report.json`（LLM，随仓库提交）与
> `tests/evals/report-offline.json`（离线，可随时由 `pytest tests/evals` 复现，不入库）。

### 9.3 持续集成

GitHub Actions（`.github/workflows/ci.yml`）：

- **backend**：ruff → Alembic 迁移 → 模拟数据（快速档）→ 知识库导入 → pytest（TimescaleDB 服务容器）；
- **frontend**：pnpm lint → pnpm build。

CI 不含真实 LLM 步骤（无 Key），因此 `runner.py --llm` 的全量指标需本地复跑；离线 Eval 由
`pytest tests/evals` 覆盖。

## 10. 项目状态

| 阶段 | 内容 | 状态 | 完成时间 |
|---|---|---|---|
| P0 | 项目初始化（骨架 / Compose / CI） | ✅ | 2026-09-29 |
| P1 | 数据层（15 张表 / hypertable / 模拟器） | ✅ | 2026-09-29 |
| P2 | Tool 层（7 工具 + 安全拦截） | ✅ | 2026-09-29 |
| P3 | Agent 层（1 Router + 4 Agent + Eval） | ✅ | 2026-09-29 |
| P4 | API 层（REST + SSE + JWT） | ✅ | 2026-09-29 |
| P5 | Web 层（5 个核心页面） | ✅ | 2026-09-29 |
| P6 | 打磨与验收（Langfuse / 报告导出 / Demo） | ✅ | 2026-09-30 |
| P7 | 加固与**验收诚实化**（窗口锚点 / Eval 口径重构 / RAG 排序与索引 / 审计收口 / 会话记忆与 grounding） | ✅ | 2026-10-03 |

> **关于 P7**：项目主体在 P0~P6 完成。P7 是对"已完成"状态做**独立复核**后的整改 ——
> 复核方式是实际跑测试、跑 Eval、连库查数、全栈冒烟，发现了三类问题并全部修复：
> ① 演示数据时效性腐烂（2 个集成测试失败、核心场景不可复现）；
> ② Eval 指标循环论证（不能作为 Agent 质量证据）；③ 若干机制缺位（审计不可见、
> RAG 关键词臂排序不确定、会话无记忆、Evidence 无 grounding）。
> 详细变更登记见 `CLAUDE.md` §11。

PRD §11 验收对照（要点，数值为 2026-10-03 实测）：

| 验收项 | 结果 |
|---|---|
| 自然语言查询设备 | ✅ 真实 Qwen 实测（EQ-003 温度峰值 92.17℃、冷却液流量 18 → 14.6 L/min 证据链） |
| Agent 正确选择工具 | ✅ 工具选择 100% (31/31 有效用例)；权限矩阵 + 越权审计留痕 |
| 读取设备时序数据 | ✅ TimescaleDB hypertable（series / stats / anomaly_windows） |
| 质量数据统计 | ✅ 近 3 天不良率 3.5% vs 基线 1.8%（EQ-003 单台 15%），Pareto 首位 surface_crack |
| 知识回答带引用来源 | ✅ 端到端引用 100% (10/10)；检索器命中 100% (22/22) |
| 生成完整诊断报告 | ✅ Evidence-based 报告落库 + Markdown 导出 |
| ≥ 30 问测试集 | ✅ 42 条（`tests/evals/testset.jsonl`），每条声明期望工具 |
| 意图 / 工具 / 引用指标 | ✅ 有效用例口径 100% / 100% / 100%（基线 90 / 95 / 90）；全量口径见 §9.2 |
| 关键结果可追溯 | ✅ 结论含数值 + 来源；审计日志覆盖全部调用结果；数值 grounding 校验 |
| 数据窗口可复现 | ✅ 窗口锚定数据末尾（`WINDOW_ANCHOR`），场景不随落库时间失效 |

已知限制：

- **默认检索是词法级的**：未配置 `EMBEDDING_BASE_URL` 时使用特征哈希实现（词袋 + 符号），
  不是语义向量；"向量臂"因此退化为第二路词法检索。生产使用需配置真实 Embedding 模型
  （bge-m3 等）并重建索引。
- **Rerank 不是模型**：`rerank_score = rrf × (1 + 0.15 × 词元重叠率)`，是可解释的轻量策略，
  非 Cross-Encoder。
- PDF / Word 文档解析尚未接入（`tools/rag/parser.py` 已预留接口，当前支持 Markdown / 纯文本）。
- 工艺分析、质量追溯、系统设置为占位页，相关能力可通过 AI 诊断页与 API 使用。
- 业务读接口（设备 / 质量 / 知识库 / 报告）当前未挂鉴权，仅 Agent 端点强制 JWT。
- 窗口锚点默认 `data`（面向回放数据集）。接入实时数据流需设 `WINDOW_ANCHOR=now`，
  否则窗口会停在数据末尾；数据滞后请以 `/api/meta/freshness` 为准。
- 工具调用次数偏高（复杂问题单次约 10~25 次），是提示词与循环上限调优空间，
  已作为指标 `tool_calls_per_case` 纳入 Eval 观测。
- 单机 Docker Compose 部署，未做水平扩展、限流与多租户隔离。

## 11. 文档索引

| 文档 | 内容 |
|---|---|
| `CLAUDE.md` | 项目执行守则（防偏移红线） |
| `05-开发计划.md` | 阶段计划与出口条件（进度基准） |
| `docs/01-产品需求文档-PRD.md` | 需求与验收标准 |
| `docs/02-架构设计文档.md` | 系统架构 |
| `docs/03-技术选型文档.md` | 技术选型 |
| `docs/04-Web页面设计文档.md` | 页面设计 |
| `docs/DEMO.md` | 演示剧本（场景 A~D） |

## 12. 贡献与许可

### 贡献

1. 开工前阅读 `CLAUDE.md`（防偏移红线）与 `05-开发计划.md`；
2. 一次改动对应一个计划任务，不夹带无关变更；
3. 新功能必须附带测试——**不写测试不算完成**；
4. 提交信息格式：`阶段-模块: 描述`（例：`P2-sql: 实现 Query Validator`）；
5. 提交前本地通过：`ruff check .` + `pytest` + `pnpm lint && pnpm build`。

### 许可

本项目基于 [Apache License 2.0](LICENSE) 开源。
