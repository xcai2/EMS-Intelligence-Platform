# Project Showcase Presentation — Design Plan
**Total time: 10 min | Slides: ~7 min | Video: 3 min**

---

## 时间分配

| 段落 | 内容 | 时长 |
|------|------|------|
| Slide 1 | Title + Team | 0:20 |
| Slide 2 | Project Scope | 1:20 |
| Slide 3 | Work Steps — Data & Architecture | 1:10 |
| Slide 4 | Work Steps — AI Intelligence Layer | 1:10 |
| Slide 5 | Key Deliverables (intro + transition to video) | 0:30 |
| **VIDEO** | **Platform demo walkthrough** | **3:00** |
| Slide 6 | Project Benefits to Flex | 1:30 |
| Slide 7 | Summary & Q&A | 0:20 |
| **Total** | | **~10:00** |

---

## Slide-by-Slide 内容设计

### Slide 1 — Title (0:20)
**标题：** EMS Competitive Intelligence Platform
**副标题：** An AI-Powered Research System for EMS Sector Analysis
**底部：** Team name · Sponsoring company: Flex Ltd · May 2026

**设计重点：** 简洁大气，一句话说清楚这是什么。

---

### Slide 2 — Project Scope (1:20)
**核心问题（左侧）：**
- Flex operates in a $200B+ EMS market with 5 major competitors
- No centralized system to monitor competitor strategy, CapEx trends, or AI investment signals in real time
- Analysts spend hours manually reading filings, news, and earnings calls

**我们的解决方案（右侧）：**
- An AI-powered platform covering **11 companies** (6 EMS + 5 hyperscalers)
- **8 functional modules**: News Intelligence, Analyst View, AI Chat, Companies Hub, AI Investments, Facilities Map, Calendar, Data Center
- Data sources: SEC EDGAR (20+ years), real-time news, earnings transcripts

**一句话定义 scope：**
> "We built a unified competitive intelligence platform — turning scattered public data into actionable insight for Flex's strategy and research teams."

---

### Slide 3 — Work Steps: Data Infrastructure (1:10)
**标题：** How We Built It — Part 1: Data Foundation

**3 个步骤（流程图风格）：**

① **Data Ingestion**
- SEC EDGAR Company Facts API → 20+ years of financial history per company
- News APIs → real-time competitor coverage
- yfinance → market data & fallback financials
- Earnings call transcripts → manual + automated ingestion

② **Data Normalization**
- 6 EMS companies with 6 different fiscal year endings → unified labeling system (FY/Q)
- XBRL concept mapping: GAAP concepts → standardized field names
- ChromaDB vector store: 10-K, 10-Q, 8-K documents → semantic search

③ **Storage Layer**
- SQLite financial cache (`aichat_financials.db`) → fast query, no LLM needed for numbers
- ChromaDB → document retrieval for qualitative analysis
- JSON caches → news, preset questions, analytics results

---

### Slide 4 — Work Steps: AI Intelligence Layer (1:10)
**标题：** How We Built It — Part 2: AI & Analytics

**4 个模块（左右双栏）：**

**RAG Pipeline**
- Retrieval-Augmented Generation over SEC filings
- Query → embedding → ChromaDB retrieval → LLM synthesis
- Sources always cited; no hallucination on financial data

**Financial Cache Short-circuit**
- Numeric financial questions (CapEx, Revenue, etc.) answered directly from SQLite
- Bypasses LLM entirely → response in <1 second vs. 15+ seconds via RAG
- Covers 11 companies × 3 financial statements × 20+ years

**Analytics Engine**
- Sentiment analysis on earnings transcripts
- CapEx anomaly detection (statistical outlier flagging)
- Investment classifier (AI strategy signal scoring)
- Geographic footprint analysis

**Frontend: Next.js Dashboard**
- 8 modules, dark/light mode, real-time streaming AI responses
- Persistent chat history, session management, table rendering

---

### Slide 5 — Key Deliverables (0:30 → video)
**标题：** What We Delivered — See It in Action

**8 deliverables（简短列表，两列）：**
- 📰 News Intelligence Feed
- 🧠 AI Analyst View (weekly themes + summaries)
- 💬 AI Chat (natural language financial queries)
- 🏢 Companies Hub (per-company deep dives)
- 📈 Hyperscaler AI Investments tracker
- 🗺️ Global Facilities Map
- 📅 Earnings & Events Calendar
- 🗄️ Data Center (filing library)

**过渡语：** "Let's walk through the platform — [start video]"

---

### Slide 6 — Project Benefits to Flex (1:30)
**标题：** Value Delivered to Flex

**三个维度：**

**⏱ Efficiency**
- Financial data retrieval: hours of manual reading → <1 second
- Competitor news monitoring: manual daily scan → automated, real-time
- Earnings call analysis: 60-page transcript → AI summary in seconds

**📊 Intelligence Quality**
- 20+ years of historical CapEx data (vs. 5 years from standard tools)
- Cross-company normalized comparisons with fiscal year alignment
- Statistical anomaly detection to flag unusual strategic shifts early

**🔭 Strategic Advantage**
- Hyperscaler CapEx trends directly inform EMS demand forecasting
- Real-time signals from 11 companies in one unified view
- Platform is extensible — new companies and data sources can be added

**底部 callout：**
> "This platform gives Flex's research team an institutional-grade intelligence capability built entirely on public data."

---

### Slide 7 — Summary & Q&A (0:20)
**标题：** Summary

**3 bullets:**
- Built an end-to-end AI research platform in one quarter
- 11 companies · 8 modules · 20+ years of data · <1 sec query response
- Open for questions

---

## 视觉风格建议

| 元素 | 建议 |
|------|------|
| 配色 | 深蓝 + 白 + 浅灰（professional, tech feel） |
| 字体 | 标题 Calibri Bold / 正文 Calibri Light |
| 图表 | 流程图用箭头串联各步骤；数字用大字号 callout |
| Logo | Flex Ltd logo 放 title slide；每页右下角小 logo |
| 截图 | Slide 5 可以放 2-3 张平台截图作为预览 |

---

## 演讲分工建议（4人团队参考）

| 段落 | 谁讲 |
|------|------|
| Slide 1-2 (Scope) | 成员 A |
| Slide 3-4 (Work Steps) | 成员 B + C |
| Slide 5 + Video | 成员 D（操作视频播放） |
| Slide 6-7 (Benefits) | 成员 A |
