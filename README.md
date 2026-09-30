# Industrial Agent

**基于大模型 Agent 的工业设备故障诊断与质量分析系统**

面向制造企业设备、工艺、质量场景的工业 AI Agent 平台：整合设备运行时序数据、工艺参数、质量检测数据与工业知识库，通过多 Agent 协同与 Tool Calling 实现设备故障诊断、工艺异常分析、质量问题溯源与自动报告生成。

> 项目执行守则以根目录 `CLAUDE.md` 为准（开工前必读）；开发进度以 `05-开发计划.md` 为唯一基准。

## 技术栈（锁定）

- **Web**：Next.js + TypeScript + shadcn/ui + Tailwind CSS + ECharts
- **后端**：FastAPI + SQLAlchemy + Pydantic + Alembic
- **Agent**：LangGraph（1 Router + 4 专业 Agent）
- **数据**：PostgreSQL + TimescaleDB + pgvector + Redis + MinIO
- **可观测性**：Langfuse（P6 接入）
- **部署**：Docker Compose + Nginx

## 目录结构

```text
industrial-agent/
├── apps/
│   ├── web/              # Next.js 前端
│   └── api/              # FastAPI 后端
├── agent/                # Router + 4 个专业 Agent
├── tools/                # SQL / TimeSeries / RAG / Analysis / Reports 工具层
├── data/                 # 数据模拟器与 fixtures
├── models/               # SQLAlchemy 数据模型
├── tests/                # 测试（含 tests/evals 后续加入）
├── docker/               # Dockerfiles / nginx / initdb
├── docs/                 # 01-PRD / 02-架构 / 03-选型 / 04-页面设计
└── docker-compose.yml
```

## 快速开始

### 方式一：Docker Compose（一键全环境）

```bash
docker compose up -d
```

- Web（经 Nginx）：http://localhost
- API 文档：http://localhost/api/docs（经 Nginx）或 http://localhost:8000/docs
- MinIO 控制台：http://localhost:9001

### 方式二：本地开发

```bash
# 后端（首次需先建虚拟环境）
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"   # Windows
cd apps/api && uvicorn app.main:app --reload       # http://localhost:8000/docs

# 前端
cd apps/web && pnpm install && pnpm dev            # http://localhost:3000（被占用时用 pnpm dev --port 3001）
```

> 本机端口约定（避开其他项目占用）：Nginx 80 · 后端 8000 · 前端直连 13000 · PostgreSQL 5432 · Redis 宿主机 16379（容器内 6379）· MinIO 9000/9001

### 数据初始化（P1 起）

```bash
docker compose up -d postgres                    # 数据库
alembic -c apps/api/alembic.ini upgrade head     # 建表 + TimescaleDB hypertable
python -m data.simulator                         # 生成模拟数据（seed=42，可复现，含场景注入）
```

- 快速档（CI / 低配机器）：`python -m data.simulator --days 2 --quality-days 5 --history-days 10`
- 生成场景清单：`data/fixtures/manifest.json`（集成测试依赖，重新种子后自动更新）
- 内置演示场景：EQ-003 主轴超温（E102）· EQ-024 停机 · LINE-2 压力波动 · PRD-A 不良率 1.8%→4.6%

### 工具层（P2 起）

7 个工具全部经 Registry → 权限矩阵 → 审计日志 执行（`tools/loader.py` 加载）：

| 工具 | 说明 |
|---|---|
| `sql.query` | 结构化白名单查询（Planner → Builder → Validator → 只读库） |
| `sql.alarm_search` | 报警代码解释 / 报警事件检索 |
| `sql.history_case` | 历史维修案例检索 |
| `timeseries.query` | 时序 series / stats / anomaly_windows（TimescaleDB） |
| `analysis.run` | 白名单统计（相关性 / z-score / IQR / 趋势 / Isolation Forest / Pareto） |
| `rag.search` | 知识库混合检索（向量+关键词 RRF + Rerank，带引用元数据） |
| `report.generate` | Evidence-based 报告生成与落库 |

```bash
python -m tools.rag ingest                # 导入知识库（6 篇示例文档 → 22 分块）
python -m tools.rag search "E102 怎么处理" # 检索调试
```

### Agent 层（P3 起）

1 Router + 4 专业 Agent（LangGraph 条件边编排，架构红线锁定）：

```text
用户问题 → Router（意图路由）
         → Equipment / Process / Quality（工具循环 → Evidence-based 结论）
         → Report（结论合并 → 结构化报告落库）
```

- LLM：OpenAI-compatible 统一接口（默认 Qwen DashScope 兼容模式，`.env` 配置 `LLM_API_KEY` 即可）
- 每个 Agent 只能调用权限矩阵内的工具；输出含数值 + 来源，可追溯
- 运行入口：`agent.runner.run_agent(query, context)`（P4 包装为 SSE API）

### Agent Eval（P3 起）

```bash
python tests/evals/runner.py           # 离线模式（无需 Key，CI 用）
python tests/evals/runner.py --llm     # LLM 模式（需 LLM_API_KEY，产出真实指标）
pytest tests/evals                     # pytest 入口
```

基线（CLAUDE.md §9）：意图 ≥90% · 工具成功率 ≥95% · RAG 引用 ≥90%；当前离线模式三项 100%（32 条测试集）。

### API 接口（P4 起）

经 Nginx（`/api/` 前缀）或后端直连（:8000）：

| 接口 | 说明 |
|---|---|
| `POST /auth/login` | 登录（演示账号 **admin / admin123**）→ JWT |
| `GET /auth/me` · `POST /auth/logout` | 当前用户 / 登出（Redis 会话吊销，不可用时降级为无状态 JWT） |
| `GET /equipment` · `GET /equipment/{id}` | 设备列表 / 详情（含活跃报警与最新传感器读数） |
| `GET /quality/summary` · `GET /quality/inspections` | 质量汇总（不良率 / Pareto / 设备分布）与明细 |
| `GET /knowledge/documents` · `POST /knowledge/search` | 知识库列表与混合检索 |
| `GET /reports` · `GET /reports/{id}` | 报告列表与详情 |
| `POST /agent/chat`（SSE） | Agent 流式对话（需登录；步骤事件 → 结果事件） |
| `GET /agent/sessions/{id}/messages` | 会话消息（需登录） |

SSE 事件流示例：`data: {"type":"step","label":"已识别：设备故障诊断","status":"done"}` … 最终 `data: {"type":"result","final_answer":"…","report_id":12}`。

### Web 页面（P5 起）

浏览器打开 http://localhost（Next.js + shadcn/ui + ECharts）：

| 页面 | 路径 | 说明 |
|---|---|---|
| Overview | `/overview` | KPI、AI 风险摘要（一键跳转分析）、设备健康、不良率趋势、活跃报警、最近分析 |
| AI 诊断 | `/ai` | SSE 流式执行步骤 + **Evidence 证据区** + 结果卡 / 报告联动（需登录 admin/admin123） |
| 设备中心 | `/equipment` | 列表（筛选 / 健康度）→ 详情（监控卡片、趋势图、告警、维修记录、AI 诊断入口） |
| 质量分析 | `/quality` | 不良率趋势、缺陷 Pareto、不良设备分布、AI 洞察与根因分析入口 |
| 知识库 | `/knowledge` | RAG 混合检索（带引用来源）+ 文档管理 |

其余占位页：工艺分析 / 报告中心（详情 `/reports/[id]` 可用）/ 系统设置。

### 架构一览

```text
Web (Next.js)  ──SSE/REST──▶  Nginx :80
                               ├──▶ FastAPI :8000        ──▶ PostgreSQL + TimescaleDB + pgvector
                               └──▶ Agent Orchestrator   ──▶ Redis / MinIO
                                        │
        Router ─▶ Equipment / Process / Quality ─▶ Report
                                        │ Tool Calling（白名单 + 权限矩阵 + 审计）
                    SQL · TimeSeries · RAG · Analysis · Alarm/Case · Report
```

> 演示剧本（场景 A~D 逐步操作）：`docs/DEMO.md`

## 常用命令

```bash
pytest                  # 后端测试（含集成测试，无数据库时自动跳过；仓库根目录执行）
ruff check .            # 后端 lint
pytest tests/evals      # Agent Eval（P3 起）
cd apps/web && pnpm lint && pnpm build   # 前端检查
```

## 文档索引

| 文档 | 内容 |
|---|---|
| `CLAUDE.md` | 项目执行守则（防偏移红线） |
| `05-开发计划.md` | 阶段计划与出口条件（进度基准） |
| `docs/01-产品需求文档-PRD.md` | 需求与验收标准 |
| `docs/02-架构设计文档.md` | 系统架构 |
| `docs/03-技术选型文档.md` | 技术选型 |
| `docs/04-Web页面设计文档.md` | 页面设计 |

## 验收对照（PRD §11）

| 验收项 | 状态 | 证据 |
|---|---|---|
| 自然语言查询设备 | ✅ | AI 诊断实测（真实 Qwen：温度峰值 92℃、流量 18→14.9 L/min 证据链） |
| Agent 正确选择工具 | ✅ | 意图路由 + 权限矩阵；Eval 工具成功率 100%（离线 29/29） |
| 读取设备时序数据 | ✅ | TimescaleDB hypertable，series/stats/anomaly_windows |
| 质量数据统计 | ✅ | 不良率 4.5% vs 基线 1.8%、Pareto、设备/班次分布（API + 页面） |
| 知识回答有引用来源 | ✅ | RAG 混合检索带 文档/章节/版本 引用；Eval 引用正确率 100%（18/18） |
| 生成完整诊断报告 | ✅ | Evidence-based 报告落库 + Markdown 导出/打印 |
| ≥30 问测试集 | ✅ | `tests/evals/testset.jsonl` 32 条 |
| 意图 ≥90% / 工具 ≥95% / 引用 ≥90% | ✅ | 离线 Eval 三项 100%；**真实 Qwen Eval：意图 100% · 工具 97.6% · 引用 100%**（12 用例） |
| 关键结果可追溯 | ✅ | 每条结论含数值 + 来源（工具/表/文档），audit 日志记录每次调用 |

## 开发状态

- [x] P0 项目初始化
- [x] P1 数据层
- [x] P2 Tool 层
- [x] P3 Agent 层
- [x] P4 API 层
- [x] P5 Web 层
- [x] P6 打磨与验收（全部完成）
