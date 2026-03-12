# Flex Competitive Intelligence Platform — UI 设计说明

本文档列出项目中所有主要 UI 设计，并用 **這個** 标注各区块/组件。

---

## 1. 全局布局 (Layout)

- **這個**：根布局 — `frontend/src/app/layout.tsx`，包含 `<html>`、`<body>`、整体 flex 容器。
- **這個**：侧边栏 — `<Sidebar />`，固定左侧 72 宽、深色渐变、全高。
- **這個**：主内容区 — `<main className="flex-1 overflow-auto bg-slate-50">`，右侧可滚动内容区域。

---

## 2. 侧边栏 (Sidebar) — `frontend/src/components/layout/Sidebar.tsx`

- **這個**：Logo 区块 — 顶部 logo、Flex Competitive Intelligence Platform 标题、「AI Powered」副标题。
- **這個**：导航列表 — Navigation 标题 + 所有 navItems（AI Chat、Dashboard、Big 5 AI CapEx 等）的链接列表。
- **這個**：导航项 — 每个链接的图标、标签、badge（如 AI、NEW）、激活态高亮与 ChevronRight。
- **這個**：Stats Card — 底部「System Active」绿点、5 Companies、18k+ Documents 统计卡片。
- **這個**：Footer 公司标签 — Flex、Jabil、Celestica、Benchmark、Sanmina 标签组。

---

## 3. 首页 (Home) — `frontend/src/app/page.tsx`

- **這個**：启动页背景 — 深色渐变 (slate-900 / purple-900)。
- **這個**：中央图标区 — Brain 图标 + Sparkles 角标、圆角与阴影。
- **這個**：标题与副标题 — 「Flex Competitive Intelligence」「AI Powered Platform」。
- **這個**：加载动画 — 三个紫色圆点 bounce 动画（会跳转到 /dashboard）。

---

## 4. 页面列表（各路由对应 UI）

- **這個**：Dashboard — `frontend/src/app/dashboard/page.tsx`（概览卡片、图表、分析师问题等）。
- **這個**：AI Chat — `frontend/src/app/chat/page.tsx`（对话区、模式切换 Documents/Web/Hybrid、输入框）。
- **這個**：Big 5 AI CapEx — `frontend/src/app/ai-investments/page.tsx`。
- **這個**：EMS Competitors — `frontend/src/app/competitor-investments/page.tsx`。
- **這個**：News Monitor — `frontend/src/app/news-monitor/page.tsx`。
- **這個**：Companies — `frontend/src/app/companies/page.tsx`。
- **這個**：Company 详情 — `frontend/src/app/companies/[company]/page.tsx`。
- **這個**：Analysis — `frontend/src/app/analysis/page.tsx`。
- **這個**：Analytics — `frontend/src/app/analytics/page.tsx`。
- **這個**：News Feed — `frontend/src/app/news/page.tsx`。
- **這個**：Calendar — `frontend/src/app/calendar/page.tsx`。
- **這個**：Heatmap — `frontend/src/app/heatmap/page.tsx`。
- **這個**：Compare — `frontend/src/app/compare/page.tsx`。
- **這個**：Sentiment — `frontend/src/app/sentiment/page.tsx`。
- **這個**：Alerts — `frontend/src/app/alerts/page.tsx`。
- **這個**：Data Mgmt — `frontend/src/app/data/page.tsx`。
- **這個**：Reports — `frontend/src/app/reports/page.tsx`。
- **這個**：Settings — `frontend/src/app/settings/page.tsx`。
- **這個**：Map — `frontend/src/app/map/page.tsx`。

---

## 5. 全局样式 (Theme) — `frontend/src/app/globals.css`

- **這個**：主题变量 — `:root` 与 `.dark` 下的 `--radius`、`--background`、`--foreground`、`--primary`、`--sidebar-*` 等。
- **這個**：Tailwind 主题扩展 — `@theme inline` 中的 `--color-*`、`--radius-*` 与 chart 颜色。

---

## 6. 通用 UI 组件 — `frontend/src/components/ui/`

- **這個**：Button — `button.tsx`（variant: default / destructive / outline / secondary / ghost / link；size: default / xs / sm / lg / icon 等）。
- **這個**：Card — `card.tsx`（CardHeader、CardTitle、CardContent、CardFooter）。
- **這個**：Input — `input.tsx`。
- **這個**：Badge — `badge.tsx`。
- **這個**：Avatar — `avatar.tsx`。
- **這個**：Tabs — `tabs.tsx`。
- **這個**：ScrollArea — `scroll-area.tsx`。
- **這個**：Separator — `separator.tsx`。
- **這個**：Skeleton — `skeleton.tsx`（DashboardSkeleton、CardSkeleton、ChartSkeleton）。
- **這個**：ChartDescription — `chart-description.tsx`（图表说明、来源、更新时间）。

---

## 7. 其他布局与功能组件

- **這個**：Leaflet 地图 — `frontend/src/components/map/LeafletMap.tsx`（Map 页使用）。

---

以上为项目中与 UI 设计相关的主要部分，均已用 **這個** 标注。
