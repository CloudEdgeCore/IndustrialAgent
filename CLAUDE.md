# CLAUDE.md — 项目执行守则（防偏移）

> 本文件是 AI 助手 / 开发者每次开工前**必读的第一文件**，规则优先级高于任何临时想法。
> 代码仓库建立后，请将本文件与 `05-开发计划.md` 一起放到仓库根目录。

## 1. 项目定位

**基于大模型 Agent 的工业设备故障诊断与质量分析系统**（作品集 / 工业 AI Demo / 企业 PoC）

- 当前状态：**全部完成**（P0~P6，2026-09-30）；进入维护 / 演示阶段
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
python -m tools.rag ingest                       # 导入知识库文档（P2 起）
cd apps/api && uvicorn app.main:app --reload     # 后端开发（http://localhost:8000）
pytest                                           # 后端测试（仓库根目录执行，含集成测试）
pytest tests/evals                               # Agent Eval（P3 起）
ruff check .                                     # 后端 lint
cd apps/web && pnpm dev                          # 前端开发（http://localhost:3000）
cd apps/web && pnpm lint && pnpm build           # 前端检查
git -c http.sslBackend=openssl -c http.proxy=http://127.0.0.1:7890 push origin main   # 推送（GitHub 直连不稳，走本机代理）
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

> **P7 加固阶段（2026-10-03 起）**：项目主体（P0~P6）已完成，本阶段只做"已验证缺陷修复 +
> 验收证据诚实化"，不新增业务范围、不替换技术栈。下列变更由用户一次性确认后执行。

| 日期 | 变更内容 | 原因 | 影响 | 确认人 |
|---|---|---|---|---|
| 2026-10-03 | 引入**窗口锚点**概念（`tools/freshness.py`，`WINDOW_ANCHOR=data\|now`）：相对时间窗口默认锚定数据最新时间，而非 `datetime.now()`；新增 `/api/meta/freshness` 与前端"数据截至"标识 | 模拟数据末尾固定在生成时刻，锚定真实时钟导致数据落库数天后"最近 24h / 最近 3 天"静默滑出数据集：2 个集成测试失败、PRD 场景 B 不可复现、界面把陈旧读数当实时展示 | 无需改断言即恢复全绿；演示可长期复现；生产改 `WINDOW_ANCHOR=now` 回归真实时钟。**不改变**长表模型与只读库防线 | 用户 |
| 2026-10-03 | 重构 Agent Eval 指标口径：意图区分 **LLM 路由**与**启发式降级**；新增**工具选择准确率**（期望工具集覆盖率 / 严格命中率）；引用改为**端到端回答命中**，检索器命中率降为诊断指标 | 原"离线意图 100%"由 `heuristic_route` 自评自测（循环论证），"工具成功率"离线模式直接执行测试集里写死的调用、LLM 模式只统计"未报错"，均不构成 Agent 质量证据 | 指标含义变化，README/计划旧数字全部重算并标注口径；验收基线数值不变（90/95/90） | 用户 |
| 2026-10-03 | RAG 检索修复：关键词臂补 `ORDER BY` 相关度排序、pgvector 增加 HNSW 索引；文档明确默认 Embedding 为词法级 | 关键词臂 `LIMIT` 前无排序，候选集为堆序（RRF 融合引入噪声）；向量列无索引为顺序扫描；默认 `DeterministicEmbedding` 为特征哈希，非语义向量 | 检索排序确定化；`document_chunks` 新增索引（新迁移）。**不新增**独立向量库 | 用户 |
| 2026-10-03 | 安全收口：权限拒绝/未知工具调用纳入审计日志；`validate_sql` 统一收口进 `run_readonly_query` | 越权尝试恰好是唯一未留痕的调用；`validate_sql` 原为各工具手动调用，`rag/search.py` 直接执行 SQL 未经校验 | 审计覆盖全部调用结果；Validator 成为执行入口的强制环节 | 用户 |
| 2026-10-03 | Agent 层：接入多轮会话历史（`run_agent(history=...)`）、结论**数值 grounding 校验**、结论解析失败显式标记 | 原实现不读历史消息、LangGraph 无 checkpointer，"会话"仅持久化展示；Evidence 契约可由占位符满足且从不校验数值是否来自工具输出；解析失败伪装为正常结论 | 会话具备真实多轮上下文；结论附带 grounding 校验结果 | 用户 |
| 2026-10-03 | 修复 Analysis Tool 缺陷：Pareto 累计 80% 边界、Spearman 并值秩、`describe` 与 SQL `stddev` 口径统一、meta 补 `source` | 统计口径不一致与边界错误会导致结论数值不可靠 | 分析数值更可靠，meta 满足可追溯要求 | 用户 |
| 2026-10-03 | 文档诚实化：README 按实测数据重写指标与限制、`05-开发计划.md` 补 P7 阶段、`CLAUDE.md` 增加 P7 说明 | 原 README 引用的"178 passed / 三项 100% / 4.5% 不良率"与实际复现结果不符 | 对外表述与可复现证据一致 | 用户 |
