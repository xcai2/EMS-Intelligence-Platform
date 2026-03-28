# News 前端说明

最后更新：2026-03-28（America/Los_Angeles）

## 1）前端模块结构

- `frontend/src/app/news/page.tsx`
  - 路由薄入口，负责渲染 News 功能组件。
- `frontend/src/features/news/NewsPageFeature.tsx`
  - News Desk 主页面实现与前端数据处理逻辑。

## 2）数据流

`NewsPageFeature.tsx` 会请求：

- `/api/news/all?count_per_company=24`
- `/api/news/industry?count=20`
- `/api/news/comparative`

点击 Refresh 后，会对同样接口加 `force_refresh=true`。

前端随后会做：
- 严格公司/噪声过滤
- 相似标题去重
- 来源质量排序
- Top News 与 Analyst View 渲染

## 3）当前页面行为（与代码一致）

- 公司切换：`All / Flex / Jabil / Celestica / Benchmark / Sanmina`
- 关键词快捷按钮：`Data Center`、`AI`、`Liquid Cooling`
- 自定义输入支持逗号分隔多关键词
- Top News：
  - Lead story：优先白名单来源，否则回退第一条
  - Trending：Top 5
  - 排除 `presentation`、`investor presentation`、`.pdf` 等
  - 优先 7 天内新闻
- Analyst View：
  - 有发布时间时优先展示最近 2 天

## 4）筛选顺序（重要）

`NewsPageFeature.tsx` 当前前端筛选顺序是：

1. 先做负向/噪声过滤（`EXCLUDED_NOISE_PATTERNS`，以及 JBL 消费电子噪声）
2. 再做严格公司匹配（`isStrictTrackedCompanyMatch`）
3. 严格公司匹配通过后即保留

重点：
- 当前前端**不是**“严格公司匹配 AND 业务关键词必须命中”的强制逻辑。
- 业务相关性仍会影响排序信号，但硬门槛是严格公司匹配。

## 5）前端来源质量规则

- 来源分级与评分在组件常量中定义。
- Lead story 白名单目前包括：
  - `finance.yahoo.com`、`reuters.com`、`bloomberg.com`、`cnbc.com`、`marketwatch.com`、`tipranks.com`

## 6）常改文件

- News 主 UI 与逻辑：
  - `frontend/src/features/news/NewsPageFeature.tsx`
- 路由壳文件：
  - `frontend/src/app/news/page.tsx`
- 侧边栏导航显示：
  - `frontend/src/components/layout/Sidebar.tsx`

## 7）校验命令

```bash
cd frontend && npm run lint -- src/features/news/NewsPageFeature.tsx src/app/news/page.tsx
```
