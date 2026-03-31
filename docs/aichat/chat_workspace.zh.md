# AI Chat 页面说明

最后更新：2026-03-31（America/Los_Angeles）

## 1）页面目的

AI Chat 是面向以下公司的分析问答工作台，支持基于 filing 的问答与 web 增强：
- Flex
- Jabil
- Celestica
- Benchmark
- Sanmina

页面重点是分析师风格的提问流程、可复用问题模板，以及可配置的 grounding/fallback 策略。

## 2）文档范围

本文是页面/产品层说明（用户看到什么、近期改了什么）。

实现文档：
- 前端：docs/aichat/frontend.zh.md
- 后端：docs/aichat/backend.zh.md

## 3）当前用户可见行为摘要

- 侧边栏有 AI Chat 入口，路径为 /chat。
- 页面路由是薄包装层，主 UI 在 feature 模块中。
- 用户可切换模式（Filing/Web/Hybrid）、选择公司并使用问题模板。
- Custom Added Questions 会持久化，并支持删除。
- 在 hybrid 模式下，发送前可配置 fallback 与 guardrails。

## 4）常用命令

重启后端：

    pkill -f "uvicorn backend.main:app --host 0.0.0.0 --port 8001"; nohup python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8001 --reload >/tmp/flex-backend.log 2>&1 &

查看后端日志：

    tail -n 40 /tmp/flex-backend.log

校验 AI Chat 前端文件：

    cd frontend && npm run lint -- src/features/chat/ChatPageFeature.tsx src/app/chat/page.tsx

## 5）变更记录

- 2026-03-31
  - AI Chat 实现迁移到 backend/aichat/* 业务目录。
  - 前端改为 feature 拆分 + app 路由薄入口（frontend/src/app/chat/page.tsx）。
  - 新增 AI Chat 独立文档集（前端/后端/页面级 + 中英版本）。
