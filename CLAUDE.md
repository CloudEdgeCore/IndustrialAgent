# CLAUDE.md — 项目执行守则（防偏移）

> 本文件是 AI 助手 / 开发者每次开工前**必读的第一文件**，规则优先级高于任何临时想法。
> 代码仓库建立后，请将本文件与 `05-开发计划.md` 一起放到仓库根目录。

## 1. 项目定位

**基于大模型 Agent 的工业设备故障诊断与质量分析系统**（作品集 / 工业 AI Demo / 企业 PoC）

- 当前状态：P1 数据层完成（2026-09-29），处于 P2 Tool 层阶段
- 文档入口：`README.md`
- 开发计划：`05-开发计划.md`（含阶段 Gate，唯一进度基准）
- 需求基准：`01-产品需求文档-PRD.md`（`docs/`）

## 2. 开工前阅读顺序

1. 本文件（CLAUDE.md）
2. `05-开发计划.md` → 当前阶段任务与出口条件
3. 改动涉及的模块设计文档章节（01/02/03/04 对应节）

## 3. 技术栈（已锁定，不得擅自替换）

| 模块 | 技术 | 禁止 |
|---|---|---|
| Web | Next.js + TypeScript | 禁止换 Vue / 其他框架 |
| UI | shadcn/ui + Tailwind CSS | 禁止引入重型组件库（AntD / MUI） |
| 图表 | Apache ECharts | 禁止换 Chart.js / D3 自研 |
| 后端 | FastAPI + SQLAlchemy + Pydantic | 禁止换 Django / Flask |
| Agent | LangGraph | 禁止回退到裸 LangChain AgentExecutor |
| LLM | OpenAI-compatible 统一接口 | 禁止硬编码单一厂商 SDK |
| 数据库 | PostgreSQL + TimescaleDB + pgvector | 禁止另起独立时序库 / 向量库 |
| 缓存 | Redis | — |
| 文件存储 | MinIO | — |
| 可观测性 | Langfuse | — |
| 部署 | Docker Compose + Nginx | MVP 不上 K8s |

新增任何依赖 / 服务前先问：设计文档里有吗？没有 → 走 §10 变更流程。

## 4. 架构红线（违反即返工）

1. **Agent 数量锁定**：1 Router + 4 专业 Agent（Equipment / Process / Quality / Report）。不新增 Agent。
2. **Agent 不直接访问数据库**，一律走 Tool Layer（Registry → 权限校验 → Executor → 数据源）。
3. **禁止 LLM 生成任意 SQL**：必须 Query Planner → 结构化 Query → SQL Builder → Validator → 只读库。
4. **AI 输出必须 Evidence-based**：问题描述 / 数据范围 / 异常发现 / 根因候选 / 证据 / 排查顺序 / 风险 / 来源，缺一不可。
5. **Analysis Tool 白名单执行**，禁止 Agent 任意执行系统代码。
6. **LLM 层必须可替换**（OpenAI-compatible 接口）。
7. **时序数据统一长表模型** `sensor_readings`（timestamp / equipment_id / sensor_type / value / quality），不设计宽表旁路。

## 5. 范围红线（MVP）

**做（PRD §10）**：20~50 台模拟设备、3 类设备、5~10 种报警、质量数据、工艺参数、设备说明书 + SOP 知识库、4 个专业 Agent、诊断中心 / 设备中心 / 质量分析 / 知识库 / 报告中心。

**不做（PRD §2.2）**：PLC 实时控制、自动修改设备参数、替代 MES / SCADA / QMS、3D 数字孪生、高风险控制闭环。**任何时候都不做，哪怕"顺便"。**

## 6. 目录结构（架构文档 §18）

```text
industrial-agent/
├── apps/web  apps/api
├── agent/router|equipment|process|quality|report
├── tools/sql|timeseries|rag|analysis|reports
├── data/simulator|fixtures
├── models/ tests/ docker/ docs/
```

新增顶层目录 / 改名需走 §10 变更流程。

## 7. 常用命令

```bash
docker compose up -d                             # 全环境（Web: http://localhost；API 文档: http://localhost/api/docs）
pip install -e ".[dev]"                          # 首次：后端依赖（仓库根目录）
alembic -c apps/api/alembic.ini upgrade head     # 数据库迁移（P1 起）
python -m data.simulator                         # 生成模拟数据（固定种子，含演示场景）
cd apps/api && uvicorn app.main:app --reload     # 后端开发（http://localhost:8000）
pytest                                           # 后端测试（仓库根目录执行，含集成测试）
pytest tests/evals                               # Agent Eval（P3 起）
ruff check .                                     # 后端 lint
cd apps/web && pnpm dev                          # 前端开发（http://localhost:3000）
cd apps/web && pnpm lint && pnpm build           # 前端检查
git -c http.proxy=http://127.0.0.1:7890 push origin main   # 推送（GitHub 直连不稳，走本机代理）
```

端口约定（避开本机其他项目占用）：Nginx 80 · 后端 8000 · 前端直连 13000 · PostgreSQL 5432 · Redis 宿主 16379（容器内 6379）· MinIO 9000/9001。

## 8. 开发流程

1. 一次只推进 `05-开发计划.md` 中的一个阶段；当前阶段 Gate 未通过不得推进。
2. 每次改动对应一个计划中的任务，不夹带无关改动。
3. 每个 Tool / Agent 完成即写测试；**不写测试不算完成**。
4. 模拟数据必须固定随机种子（可复现）。
5. 提交信息格式：`阶段-模块: 描述`（例：`P2-sql: 实现 Query Validator`）。
6. **每完成一步（一个任务 / 子任务）立即提交并推送**（命令见 §7），不攒批量；推送失败时重试，不得跳过。

## 9. 验收基线（量化，P3 / P6 对照）

- 测试集 ≥30 条工业问题
- 意图分类准确率 ≥90%
- Tool 调用成功率 ≥95%
- RAG 引用正确率 ≥90%
- 关键分析结果可追溯（带数据来源）

## 10. 变更流程（唯一合法偏移通道）

任何超范围需求或技术替换：

1. 在本文件 §11 变更记录登记（日期 / 内容 / 原因 / 影响）；
2. 评估对里程碑与 Gate 的影响；
3. 用户确认后执行。

**未登记即实现 = 违规，需回滚。**

## 11. 变更记录

| 日期 | 变更内容 | 原因 | 影响 | 确认人 |
|---|---|---|---|---|
| — | （待登记） | — | — | — |
