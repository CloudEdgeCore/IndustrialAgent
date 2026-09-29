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

### 常用命令

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

## 开发状态

- [x] P0 项目初始化
- [x] P1 数据层
- [ ] P2 Tool 层
- [ ] P3 Agent 层
- [ ] P4 API 层
- [ ] P5 Web 层
- [ ] P6 打磨与验收
