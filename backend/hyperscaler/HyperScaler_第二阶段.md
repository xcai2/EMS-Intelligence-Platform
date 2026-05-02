# HyperScaler 第二阶段

最后更新：2026-05-01

## 1. 第二阶段目标

第一阶段已经完成：

- Gemini API 接入，固定一个主问题获取 Big 5 CapEx 数据
- 缓存机制：`big5_capex_api_raw.json` + `big5_capex_view_model.json`
- 页面加载读缓存，Refresh 触发重新调用 Gemini

第二阶段的目标是**优化 Gemini 的提问方式**，让回答更稳定、边界更清晰、数据质量更高。

核心问题：第一阶段用一个大问题问所有字段，Gemini 的回答结构可能不稳定，某些字段可能混在一起或缺失。第二阶段要解决这个问题。

---

## 2. 第二阶段与第一阶段的关系

第一阶段的文件结构和接口路径全部保留：

```text
backend/hyperscaler/
data/hyperscaler/big5_capex_api_raw.json
data/hyperscaler/big5_capex_view_model.json
GET /api/intelligence/big5-capex
DELETE /api/intelligence/hyperscaler/guidance/cache
```

第二阶段只修改 `questions.py` 和 `service.py` 里的提问和解析逻辑，不改接口路径，不改前端，不改缓存文件结构。

---

## 3. 第二阶段核心升级：多问题模板

第一阶段用一个主问题覆盖所有字段。第二阶段改成按字段分组，发多个小问题，每个问题边界清晰。

### 3.1 问题分组建议

```python
QUESTION_TEMPLATES = {
    "capex_outlook": {
        "target_fields": ["capex_2026_billions", "capex_2025_billions", "yoy_growth_pct"],
        "question": "...",
    },
    "ai_focus": {
        "target_fields": ["ai_focus_areas"],
        "question": "...",
    },
    "announcements": {
        "target_fields": ["recent_announcements"],
        "question": "...",
    },
    "key_metrics": {
        "target_fields": ["key_metrics"],
        "question": "...",
    },
    "stargate": {
        "target_fields": ["stargate_project"],
        "question": "...",
    },
}
```

每个问题只要求 Gemini 回答对应字段，不混在一起。

### 3.2 问题边界规则

每个问题模板必须写明：

- 目标字段是哪些
- 期望返回格式（数字、数组、对象）
- 字段缺失时返回什么（`null`、`[]`、`{}`）
- 是否需要带上一次缓存作为上下文

### 3.3 什么时候带上下文

不需要上下文：

```text
capex_outlook    直接问最新数字，不需要对比
stargate         直接问项目详情
```

需要带上下文：

```text
announcements    需要知道上次已有哪些，避免重复
ai_focus         需要知道上次已有哪些，判断是否有新增
```

带上下文时只传最小必要字段，不把整个缓存文件塞给 Gemini。

---

## 4. 字段级更新规则

第二阶段多问题合并结果时，必须区分三种状态：

| 状态 | 含义 | 处理方式 |
|---|---|---|
| `new_value_found` | Gemini 本次明确返回了新值 | 覆盖旧值 |
| `not_mentioned` | Gemini 本次没提到该字段 | 保留旧值，不清空 |
| `explicit_empty` | Gemini 明确说没有或撤回 | 清空，记录原因 |

这样可以避免某个问题没覆盖到某个字段时，误把旧值清空。

---

## 5. 新增文件

第二阶段在 `backend/hyperscaler/` 下新增：

```text
refresh_service.py   执行多问题刷新流程，合并结果，写缓存
```

`questions.py` 从第一阶段的单问题扩展为多问题模板，职责不变。

其余文件（`models.py`、`cache.py`、`service.py`、`gemini_client.py`、`financials.py`、`routes.py`）保持不动。

### `refresh_service.py` 职责

```text
按问题分组依次调用 Gemini
-> 收集每个问题的回答
-> 合并成完整 payload（字段级合并，不是覆盖）
-> 对比上一次缓存（字段级 diff）
-> 有变化则写入新缓存
-> 无变化返回 no_change
-> 写 big5_capex_api_raw.json（调试用）
```

---

## 6. 刷新结果对比

第二阶段 Refresh 不能简单覆盖缓存，必须先做字段级对比：

```text
new merged payload
-> compare with big5_capex_view_model.json
-> if changed: write new cache, return refresh_status="updated"
-> if unchanged: keep current cache, return refresh_status="no_change"
-> if error: keep current cache, return refresh_status="error"
```

`DELETE /hyperscaler/guidance/cache` 返回结构：

```json
{
  "refresh_status": "updated",
  "changed": true,
  "changed_fields": ["companies.AMZN.capex_2026_billions"]
}
```

```json
{
  "refresh_status": "no_change",
  "changed": false,
  "changed_fields": []
}
```

```json
{
  "refresh_status": "error",
  "changed": false,
  "error": "Gemini API request failed",
  "cache_preserved": true
}
```

---

## 7. 安全边界

第二阶段不变：

- 前端只发 refresh 请求，不传问题内容
- 问题模板固定在后端 `questions.py`
- Gemini 原始回答不直接给前端
- 前端只消费归一化后的 `view_model`

---

## 8. 验收标准

接口行为：

```bash
# 页面加载读缓存
curl http://localhost:8001/api/intelligence/big5-capex

# Refresh 触发多问题更新并返回 diff
curl -X DELETE http://localhost:8001/api/intelligence/hyperscaler/guidance/cache
```

数据质量：

- 每个字段来自明确的对应问题，不混用
- 字段缺失时保持 `null`/`[]`/`{}`，不清空旧值
- 有变化时返回 `changed_fields` 列表
- Gemini 失败时页面继续显示旧缓存

---

## 9. 第三阶段升级空间

第二阶段完成后，可以继续：

- 增加每个数字的来源引用（`source_text`）
- 增加 confidence 标注
- 增加 SEC filing 或 earnings transcript 数字对照
- 增加定时后台自动刷新
- LLM Summary 用于文字说明（不用于补数字）
