# 工业设备智能诊断与质量分析 Agent 平台
## Web 端页面设计文档

## 1. 设计定位

产品定位：

**工业 AI 决策工作台**

不是传统 MES 风格，也不是普通聊天机器人。

视觉关键词：

- 工业；
- 数据；
- 智能；
- 专业；
- 克制；
- 高信息密度。

整体建议：

- Desktop First；
- 1440px 主设计尺寸；
- 深色 / 浅色均可；
- 默认浅色专业工业风；
- AI 区域适当使用渐变和高亮。

---

## 2. 信息架构

左侧导航：

```text
Overview
AI 诊断
设备中心
工艺分析
质量分析
知识库
报告中心
系统设置
```

顶部：

```text
工厂 / 产线选择
全局搜索
告警
用户
```

---

## 3. 首页 Overview

目标：

让用户 10 秒内了解工厂当前状态。

页面结构：

```text
┌──────────────────────────────────────────┐
│ Overview                     Plant A     │
├─────────┬─────────┬─────────┬────────────┤
│设备总数 │告警设备 │今日异常 │今日不良率   │
├─────────┴─────────┴─────────┴────────────┤
│            AI Risk Summary               │
├──────────────────┬───────────────────────┤
│ Equipment Health │ Quality Trend         │
├──────────────────┼───────────────────────┤
│ Active Alarms    │ Recent AI Analysis    │
└──────────────────┴───────────────────────┘
```

卡片：

- 设备运行率；
- 告警设备；
- 未处理报警；
- 今日不良率；
- AI 风险摘要。

AI Risk Summary：

```text
AI 发现 3 个需要关注的问题

● 3 号设备主轴温度持续升高
● A 产品不良率较昨日增加 2.1%
● 2 号产线压力波动异常

[立即分析]
```

---

## 4. AI 诊断中心

这是整个产品核心页面。

布局：

```text
┌─────────────┬────────────────────────────┐
│ Conversation│       AI Workspace         │
│ History     │                            │
│             │ User Question              │
│             │                            │
│             │ Agent Execution            │
│             │                            │
│             │ Evidence                   │
│             │                            │
│             │ Final Analysis             │
└─────────────┴────────────────────────────┘
```

输入框提示：

```text
询问设备、工艺或质量问题，例如：
“分析 3 号设备过去 2 小时温度异常原因”
```

快捷问题：

- 分析设备故障；
- 分析质量异常；
- 查询报警代码；
- 分析工艺参数；
- 生成日报。

---

## 5. Agent 执行过程 UI

不要展示模型“思维链”。

只展示业务执行步骤：

```text
分析任务

✓ 已识别：设备故障诊断
✓ 查询设备运行数据
✓ 查询 E102 报警
✓ 检索历史维修记录
✓ 检索设备手册
✓ 执行异常分析

正在生成诊断结果...
```

---

## 6. Evidence 证据区

这是产品核心差异。

每个 AI 结论下面展示：

```text
证据

设备数据
主轴温度：87.4℃
正常范围：40~80℃

历史数据
过去 30 天出现 4 次类似异常

知识库
《X200 主轴系统维护手册》
第 42 页

维修记录
2026-07-18
冷却过滤器堵塞
```

用户可以展开查看原数据。

---

## 7. AI 分析结果卡

示例：

```text
诊断结果

高风险

可能原因
1. 冷却系统效率下降        高
2. 主轴轴承异常            中
3. 温度传感器漂移          低

建议排查顺序

01 检查冷却液流量
02 检查冷却泵
03 检查过滤器
04 检查轴承振动

[生成报告]
```

---

## 8. 设备中心

设备列表：

```text
设备名称
设备编号
类型
运行状态
健康度
当前告警
最后更新时间
```

支持：

- 搜索；
- 设备类型；
- 状态；
- 产线筛选。

设备状态：

```text
正常
关注
告警
停机
```

---

## 9. 设备详情

顶部：

```text
CNC-003
3 号数控加工中心

运行中
Health 78
```

Tabs：

```text
实时监控
趋势分析
告警
维修记录
AI 诊断
```

实时监控：

卡片：

- 温度；
- 振动；
- 电流；
- 转速；
- 压力。

下面：

多指标趋势图。

---

## 10. 工艺分析页

布局：

```text
工艺参数
────────────────

时间范围
产品
产线
设备

[Temperature]
[Pressure]
[Speed]
[Flow]

────────────────

Process Trend

────────────────

AI Insights

“15:20-16:05 压力波动异常，
与阀门开度变化高度相关。”

[详细分析]
```

---

## 11. 质量分析页

顶部 KPI：

- 今日产量；
- 合格率；
- 不良率；
- 缺陷数。

图表：

1. 不良率趋势；
2. 缺陷 Pareto；
3. 产品分布；
4. 班次对比；
5. 设备对比。

AI Quality Insight：

```text
A 产品不良率过去 3 天明显升高。

主要集中：
设备：CNC-003
班次：Night Shift
缺陷：Surface Crack

[AI 根因分析]
```

---

## 12. 质量追溯页面

选择：

```text
Product
Batch
Date
```

系统生成：

```text
Batch B20260928001

Material
↓
Process
↓
Equipment
↓
Inspection
↓
Defect
```

支持点击节点查看数据。

---

## 13. 知识库

页面布局：

```text
Knowledge Base

[Upload]

All Documents
Equipment Manual
SOP
Quality
Maintenance
Alarm
```

列表：

```text
Document
Type
Equipment
Version
Chunks
Status
Updated
```

点击文档：

右侧 Drawer 显示：

- 文档信息；
- chunk；
- metadata；
- AI 可检索状态。

---

## 14. 报告中心

列表：

```text
Report
Type
Equipment
Created By
Time
Status
```

报告详情：

```text
Industrial AI Analysis Report

Summary
Problem
Data
Analysis
Root Cause
Evidence
Recommendation
Risk
```

支持：

- PDF；
- Markdown；
- 打印。

---

## 15. 系统设置

模块：

- LLM；
- Embedding；
- 数据源；
- Agent；
- 用户；
- 权限；
- 日志。

Agent 设置：

```text
Equipment Agent     Enabled
Process Agent       Enabled
Quality Agent       Enabled
Report Agent        Enabled
```

---

## 16. 颜色与视觉建议

不要做传统“蓝色后台系统”。

建议：

基础：

```text
Background: #F7F8FA
Surface: #FFFFFF
Text: #111827
Secondary: #6B7280
Border: #E5E7EB
```

状态：

```text
Normal: Green
Warning: Amber
Critical: Red
AI: Indigo / Violet
```

图表颜色保持克制。

---

## 17. 字体

中文：

- PingFang SC；
- Microsoft YaHei；
- 思源黑体。

英文 / 数字：

- Inter；
- Geist。

数据面板建议使用 Tabular Numbers。

---

## 18. 关键交互

### AI + 页面联动

用户在设备详情点击：

```text
AI Diagnose
```

自动把：

```text
equipment_id
time_range
active_alarms
```

作为 Context 传给 Agent。

因此用户无需再次输入：

> “帮我分析这台设备。”

---

## 19. 页面路由

```text
/
├── /overview
├── /ai
├── /equipment
│   └── /equipment/[id]
├── /process
├── /quality
│   └── /quality/trace
├── /knowledge
├── /reports
│   └── /reports/[id]
└── /settings
```

---

## 20. Web Demo 最重要的 5 个页面

如果时间有限，优先完成：

1. Overview
2. AI Diagnosis
3. Equipment Detail
4. Quality Analysis
5. Knowledge Base

这 5 个页面已经足够完整展示项目。

---

## 21. Google Stitch / AI UI 生成提示词

```text
Design a professional desktop web application for an Industrial AI Agent platform.

Product name: Industrial Insight AI

The platform helps manufacturing engineers diagnose equipment failures, analyze process anomalies, trace quality problems and query industrial knowledge using AI agents.

Style:
- Modern enterprise industrial AI
- Clean, minimal and high information density
- Apple-inspired spacing and polish
- Light background
- White cards
- Subtle borders
- Professional typography
- Avoid traditional outdated admin dashboard style

Layout:
- Left sidebar navigation
- Top navigation bar
- Main dashboard workspace

Sidebar:
Overview
AI Diagnosis
Equipment
Process Analysis
Quality Analysis
Knowledge Base
Reports
Settings

Dashboard widgets:
Equipment Health
Active Alarms
Today's Defect Rate
Production Quality
AI Risk Summary
Equipment Trend
Quality Trend
Recent AI Analysis

AI Diagnosis page:
- Chat interface
- Agent execution status
- Tool execution timeline
- Evidence panel
- Industrial data cards
- AI diagnosis result
- Root cause candidates
- Confidence level
- Recommended troubleshooting steps
- Generate Report button

Equipment detail page:
- Equipment status
- Health score
- Sensor cards
- Temperature
- Vibration
- Pressure
- RPM
- Time-series charts
- Alarm history
- Maintenance records
- AI Diagnose button

Quality Analysis:
- Quality KPI cards
- Defect rate trend
- Pareto defect chart
- Batch analysis
- Equipment comparison
- AI quality insight card

Use charts inspired by professional industrial monitoring software but maintain a modern AI SaaS visual language.
Desktop width: 1440px.
```
