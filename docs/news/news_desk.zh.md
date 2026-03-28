# News Desk 页面说明

最后更新：2026-03-28（America/Los_Angeles）

## 1）用途

`News Desk` 是以下 5 家公司的主新闻监控页：
- Flex
- Jabil
- Celestica
- Benchmark
- Sanmina

页面目标是快速阅读与判断（Top News + Analyst View），并支持手动刷新。

## 2）本文档范围

这是**页面/产品级**说明（用户看到什么、近期改了什么）。

实现细节请看：
- 前端：`docs/news/frontend.zh.md`
- 后端：`docs/news/backend.zh.md`

## 3）当前用户可见行为（摘要）

- 侧边栏中 News 入口位于 `NEWs` 分组（路径 `/news`）。
- 页面默认读取后端缓存结果。
- 点击 `Refresh` 会触发后端 `force_refresh=true`。
- 公司和关键词控件会在页面内影响筛选与排序。

## 4）常用命令

重启后端：
```bash
pkill -f "uvicorn backend.main:app --host 0.0.0.0 --port 8001"; nohup python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8001 --reload >/tmp/flex-backend.log 2>&1 &
```

查看后端日志：
```bash
tail -n 40 /tmp/flex-backend.log
```

News 前端文件 lint：
```bash
cd frontend && npm run lint -- src/features/news/NewsPageFeature.tsx src/app/news/page.tsx
```

## 5）更新记录

- 2026-03-28
  - 按当前代码重新核对并修正文档。
  - 更新前端行为说明（快捷关键词、Top News 与 fast-feed 时间窗口）。
  - 更新后端说明（有效接口、数据源组合、service 与 aggregator 的缓存差异）。

- 2026-03-27
  - News 实现迁移到 `backend/news/*` 业务目录。
  - 删除 `backend/ingestion/` 下兼容层。
  - 文档拆分为前端/后端/页面级三份。
