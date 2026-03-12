# Flex Competitive Intelligence Platform - UI Design Spec

本文档用于定义项目后续 UI 精修的统一标准，覆盖页面位置、导航结构、颜色体系、按钮命名、文案语气与交互层级。

目标不是“把页面做满”，而是让用户在 3 秒内明白：

1. 这是一个什么产品
2. 现在应该先看哪里
3. 每个按钮按下去会发生什么

---

## 1. 设计目标

### 核心定位

这是一个面向分析师和研究人员的竞争情报平台，核心任务是：

- 跟踪 EMS 行业五家公司
- 分析 AI / Data Center / CapEx 投资动态
- 快速查看财务、新闻、地理扩张与情绪变化
- 通过 AI Chat 做研究提问与交叉对比

### 设计原则

- 信息优先：先让用户找到结论，再看细节
- 层级明确：每页只能有一个主动作
- 文案专业：避免“炫技式 AI 文案”
- 视觉克制：用科技感，但不做霓虹面板
- 统一命名：页面名、按钮名、卡片标题必须同一套语言

---

## 2. 信息架构

当前页面较多，导航层级偏平，容易让用户失焦。后续改为 4 组结构。

### A. Overview

- Dashboard
- AI Chat
- Companies

### B. Intelligence

- AI Investment Tracker
- Competitor Compare
- News Monitor
- Earnings Calendar

### C. Analysis

- Financial Analysis
- Sentiment
- Geographic Footprint
- Alerts

### D. System

- Reports
- Data Center
- Settings

### 导航重命名建议

| 当前名称 | 建议名称 | 原因 |
|----------|----------|------|
| AI Chat | Research Chat | 更像研究工具，不像客服聊天 |
| Big 5 AI CapEx | AI Investment Tracker | 更短，更像产品模块 |
| EMS Competitors | Competitor Compare | 更明确地表示对比动作 |
| Analysis | Financial Analysis | 和 Analytics 区分开 |
| Analytics | Market Intelligence | 避免与 Analysis 重复 |
| News Feed | News Archive | 和 News Monitor 区分 |
| Heatmap | Geographic Footprint | 用户更容易理解 |
| Compare | Compare Companies | 动词更完整 |
| Data Mgmt | Data Center | 更像平台管理页 |

### 侧边栏顺序建议

1. Dashboard
2. Research Chat
3. Companies
4. AI Investment Tracker
5. Competitor Compare
6. News Monitor
7. Earnings Calendar
8. Financial Analysis
9. Sentiment
10. Geographic Footprint
11. Alerts
12. Reports
13. Data Center
14. Settings

说明：

- 高频页面放前面
- “看全局 -> 找公司 -> 做分析 -> 导出报告”形成自然路径
- 减少 Dashboard 和多个分析页之间的抢权重问题

---

## 3. 页面布局规范

### 全局布局

- 左侧固定导航：宽度 `280px`
- 顶部不再额外加全局 header
- 主内容区最大宽度：`1440px`
- 页面内容左右内边距：
  - Desktop: `32px`
  - Tablet: `24px`
  - Mobile: `16px`

### 标准页面结构

每个页面统一采用以下 5 段结构：

1. Page Header
2. KPI Strip
3. Primary Panel
4. Secondary Analysis Grid
5. Source / Update Footer

### Page Header 组成

- 左侧：页面标题 + 一句功能说明
- 右侧：1 个主按钮 + 1 到 2 个次按钮

示例：

- 页面标题：`AI Investment Tracker`
- 说明：`Track AI infrastructure spending, customer exposure, and capacity expansion across the Big 5 EMS companies.`
- 主按钮：`Run Analysis`
- 次按钮：`Export`
- 次按钮：`Refresh Data`

### KPI Strip 规范

- 每页最多 4 个 KPI 卡片
- 每张卡片只放一个主数字
- 数字下必须有解释标签
- 避免同一卡片同时放趋势、说明、图标、按钮四类内容

---

## 4. 视觉风格

当前界面偏“蓝紫科技风”，但紫色使用过多，且多个页面背景策略不一致。后续统一为：

### 主风格方向

- 基础气质：Institutional Tech
- 关键词：clean, analytical, confident, restrained
- 避免：
  - 大面积紫色
  - 高饱和渐变泛滥
  - 过多玻璃拟态
  - 每个卡片都带重阴影

### 主色板

#### Brand

- `Brand Navy`: `#0F172A`
- `Brand Blue`: `#2563EB`
- `Brand Cyan`: `#0891B2`

#### Surface

- `Canvas`: `#F8FAFC`
- `Panel`: `#FFFFFF`
- `Panel Alt`: `#F1F5F9`
- `Border`: `#E2E8F0`

#### Text

- `Text Strong`: `#0F172A`
- `Text Base`: `#334155`
- `Text Muted`: `#64748B`

#### Semantic

- `Success`: `#16A34A`
- `Warning`: `#D97706`
- `Danger`: `#DC2626`
- `Info`: `#0EA5E9`

### 公司颜色

只用于图表、标签、地图点，不用于大面积背景。

- Flex: `#2563EB`
- Jabil: `#059669`
- Celestica: `#7C3AED`
- Benchmark: `#D97706`
- Sanmina: `#DC2626`

### 背景策略

- Dashboard / Analysis 页：浅色背景，白卡片
- Chat 页：更安静的灰蓝背景
- Landing / Splash 页：可以保留深色，但仅首页使用

---

## 5. 按钮系统

按钮名称需要像金融研究软件，不要像营销页。

### 按钮层级

#### Primary

用于页面唯一主动作。

样式建议：

- 背景：`Brand Blue`
- 文字：白色
- Hover：加深 6% 到 8%

常用文案：

- `Run Analysis`
- `Generate Report`
- `Ask Question`
- `Export Report`
- `Compare Companies`

#### Secondary

用于辅助动作。

样式建议：

- 白底
- 灰边
- 深色文字

常用文案：

- `Refresh Data`
- `View Details`
- `Open Filing`
- `See Sources`
- `Manage Alerts`

#### Tertiary / Ghost

用于低干扰动作。

常用文案：

- `Clear`
- `Hide`
- `Collapse`
- `Back`

### 按钮命名规则

- 优先使用动词开头
- 不要使用模糊词：
  - 不建议：`Submit`
  - 不建议：`Process`
  - 不建议：`Click Here`
- 使用结果明确的词：
  - 建议：`Run Analysis`
  - 建议：`Export CSV`
  - 建议：`Open Company Page`

### 当前按钮文案调整建议

| 当前位置 | 当前文案 | 建议文案 |
|----------|----------|----------|
| Chat | Documents | Filing Search |
| Chat | Web | Web Search |
| Chat | Hybrid | Hybrid Search |
| Chat | Clear | Clear Chat |
| Companies | Refresh | Refresh Data |
| Dashboard 错误态 | Retry Connection | Reconnect |
| Companies 错误态 | Retry | Try Again |
| Sidebar | Data Mgmt | Data Center |

---

## 6. 页面级设计建议

### Dashboard

目标：

- 先看行业，再看公司，再看风险

页面顺序建议：

1. 顶部 KPI
2. Big 5 company snapshot
3. AI investment ranking
4. anomaly / alert panel
5. recent news and questions

主按钮：

- `Run Full Analysis`

次按钮：

- `Export Brief`
- `Refresh Data`

### Research Chat

目标：

- 像研究终端，不像普通聊天框

布局建议：

- 左侧：suggested prompts
- 中间：conversation
- 右侧：retrieval mode + source settings

当前问题：

- 模式按钮太轻，像 tabs，不像核心检索控制
- 默认空状态不错，但可进一步强化“研究模板”

按钮建议：

- `Ask Question`
- `Clear Chat`
- `Use Prompt`

模式名称：

- `Filing Search`
- `Web Search`
- `Hybrid Search`

### Companies

目标：

- 成为五家公司总入口页

布局建议：

- 顶部放筛选：company size / AI focus / region
- 卡片点击进入详情
- 卡片底部固定三个指标：
  - AI Focus
  - Sentiment
  - Facility Count

主按钮：

- `Compare Companies`

次按钮：

- `Refresh Data`

### Company Detail

每个公司详情页统一 6 个区块：

1. Company header
2. Key metrics
3. AI / CapEx summary
4. filing and earnings timeline
5. geographic footprint
6. latest news and signals

### News Monitor

目标：

- 看“新发生了什么”

必须突出：

- 时间
- 事件类型
- 影响公司
- 影响主题

主按钮：

- `Create Alert`

### Reports

目标：

- 让用户一键带走分析结果

主按钮：

- `Generate Report`

次按钮：

- `Export PDF`
- `Export Excel`

---

## 7. 文案语气

### 应该使用的语气

- 简洁
- 研究型
- 低情绪化
- 明确结论导向

### 避免的语气

- “powerful”
- “amazing”
- “smart insights”
- “cutting-edge AI”

### 标题写法建议

- 好：`AI Investment Outlook`
- 好：`Recent Capacity Expansion`
- 好：`Cross-Company CapEx Comparison`
- 一般：`Advanced Analytics Dashboard`
- 一般：`Intelligent Business Insights`

---

## 8. 组件规范

### 卡片

- 默认圆角：`20px`
- 默认边框：`1px solid Border`
- 阴影：轻阴影，仅 hover 增强
- 内边距：
  - 大卡片：`24px`
  - 小卡片：`16px`

### Badge

只用于四类信息：

- 状态
- 公司 ticker
- 分类标签
- 数据来源

不要把 badge 当按钮使用。

### 图标

- 每个区域只保留一个主图标
- 不要每一行都配图标
- 图标只辅助扫描，不应成为主视觉噪音

### 图表

- 先柱状图和折线图，少用炫技型图表
- 图例必须能直接对应公司颜色
- 图表标题必须带时间范围

---

## 9. 响应式规则

### Desktop

- 以双列或三列布局为主

### Tablet

- 侧边栏变窄或折叠
- KPI 变成两列

### Mobile

- 侧边栏改抽屉
- 页面 header 按钮只保留主按钮
- 图表优先变为纵向卡片

---

## 10. 当前实现的主要问题

基于当前代码，已有几个明显需要统一的点：

1. 页面命名重复
2. 紫色使用偏多，品牌感不稳定
3. 部分按钮命名过于泛
4. Dashboard、Analysis、Analytics 边界不清
5. Sidebar 信息密度高，但分组弱
6. 首页 splash 风格与内部页面割裂较大

---

## 11. 设计落地顺序

后续 UI 精修建议按以下顺序推进：

1. 先统一全局设计 token
2. 再重做 sidebar 和 page header
3. 再改 Dashboard
4. 再改 Chat
5. 再改 Companies 和 Company Detail
6. 最后统一其余分析页

这样做的原因：

- 先改 token，后面页面不会反复返工
- 先改高频页，收益最大

---

## 12. 下一步执行建议

如果开始进入实际改稿，建议直接分三步：

1. 先改 `layout.tsx`、`Sidebar.tsx`、`globals.css`
2. 再改 `dashboard/page.tsx`
3. 再改 `chat/page.tsx`

对应目标：

- 先统一框架
- 再建立视觉锚点
- 再提升最核心工作流

---

## 13. 本阶段结论

这次 UI 精修不建议继续“补页面”，而应该先做三件事：

- 统一导航与页面命名
- 收敛颜色体系
- 规范按钮语言

只要这三件事先完成，后面的页面优化就会顺很多。
