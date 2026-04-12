# 新闻过滤层维护手册

最后更新：2026-04-10

---

## 一、架构原则

```
抓取层  →  召回尽量多
过滤层  →  负责精度
前端    →  只负责展示
```

过滤逻辑集中在后端，调整时**只改下面列出的几个位置**，不动抓取层，不改主流程代码。

---

## 二、维护入口一览

| 要改什么 | 改哪个文件 | 改哪个位置 |
|---|---|---|
| 某公司的噪声词（误命中的词组） | `sources.py` | 对应公司的 `excluded_noise_terms` |
| 某公司是否启用严格 title 匹配 | `sources.py` | 对应公司的 `strict_title_match` |
| 某公司的别名（用于搜索和匹配） | `sources.py` | 对应公司的 `aliases` |
| 全局噪声词（所有公司共用） | `filtering.py` | `EXCLUDED_NOISE_TERMS` |
| 公司相关性判断的核心逻辑 | `news_filter_policies.py` | `is_company_related_item()` |
| 新增一家公司 | `sources.py` + `core/config.py` | 见第五节 |

---

## 三、最常见操作：补 excluded_noise_terms

**场景**：force_refresh 之后，主列表里出现了和某公司无关的文章。

**操作步骤**：

1. 看文章标题/描述，找到触发匹配的词组（通常是公司 alias 出现在 description 里）。
2. 打开 `backend/news/sources.py`，找到对应公司的 `excluded_noise_terms` 列表。
3. 把这个词组加进去，用小写，词组越具体越好（避免误伤）。
4. 重启后端，触发 force_refresh，验证该条目不再出现。

**示例**：发现 FLEX 的列表里混进了"flex schedule"相关的人力资源文章：

```python
# sources.py → FLEX → excluded_noise_terms
"excluded_noise_terms": [
    ...
    "flex schedule",   # ← 新增这一行
],
```

**原则**：词组要尽量精确，避免用单个词。比如不要加 `"flex"`，要加 `"flex schedule"`。

---

## 四、strict_title_match 说明

控制"alias 出现在 description 但不在 title 里"时是否放行。

| 值 | 行为 | 适用公司 |
|---|---|---|
| `True` | description 里仅有单词 alias 命中 → 拒绝 | FLEX、BHE（短名是常用英文词） |
| `False` | description 里 alias 命中 → 放行 | JBL、CLS、SANM、PLXS（名字辨识度高） |

**如果发现某家公司 description-only 文章误命中严重，把它改成 `True`。**

```python
# sources.py
"SANM": {
    ...
    "strict_title_match": True,   # 改为 True 后：description 里的 "Sanmina" 不再触发放行
},
```

---

## 五、新增公司

在两个文件里各加一段配置，主流程代码**不需要改**。

### 5.1 `backend/core/config.py` → `COMPANIES`

```python
"XXXX": {
    "name": "公司全称",
    "cik": "0000000000",          # SEC CIK 编号
    "sector": "EMS",
    "description": "一行描述",
},
```

同时在 `COMPANY_NAME_TO_TICKER` 里加：

```python
"短名": "XXXX",
```

### 5.2 `backend/news/sources.py` → `OFFICIAL_COMPANY_SOURCES`

```python
"XXXX": {
    "name": "短名",
    "domain": "example.com",
    "base_url": "https://www.example.com",
    "news_url": "https://www.example.com/news/",
    "rss_url": [
        "https://ir.example.com/rss/pressrelease.aspx",    # 优先找 IR 站的 RSS
    ],
    "public_news_url": None,
    "aliases": ["公司全称", "NYSE:XXXX"],
    # 短名是否是常用英文词？是 → True，否 → False
    "strict_title_match": False,
    # 已知会误命中的词组，留空也可以，后续运营中补充
    "excluded_noise_terms": [],
},
```

配置加完后，第一次请求这家公司的新闻时会自动触发抓取（无需手动 force_refresh）。

---

## 六、判断逻辑流程（供调试参考）

`is_company_related_item()` 在 `news_filter_policies.py` 里，判断顺序如下：

```
输入：一条 normalized news item + ticker + company_name

Step 1  excluded_noise_terms 命中 title 或 description？
        → 是：直接拒绝，终止

Step 2  文章 URL 域名 ∈ 公司 official domain？
        → 是：直接接受（官方来源无条件放行）

Step 3  任意 alias 出现在 title 里？
        → 是：接受

Step 4  多词 alias（含空格）出现在 description 里？
        → 是：接受（"Flex Ltd"、"Benchmark Electronics" 等多词 alias 辨识度高）

Step 5  item.source 字段包含公司短名？
        → 是：接受

Step 6  strict_title_match == False 且 任意 alias 出现在 description？
        → 是：接受
        （strict_title_match == True 的公司在此处直接跳过）

结果：以上都未命中 → 拒绝
```

---

## 七、全局噪声词（filtering.py）

`EXCLUDED_NOISE_TERMS` 在 `normalize_result()` 里最先执行，作用于**所有公司**。

适合放这里的词：所有公司都不需要的内容类型（体育联盟、招聘广告等）。

**不要**把公司专属的噪声词放这里，放 `sources.py` 的 `excluded_noise_terms`。

```python
# filtering.py
EXCLUDED_NOISE_TERMS = [
    "fiba",
    "nba",
    "nfl",
    "nhl",
    "mlb",
    "job opening",
    "job posting",
    "we are hiring",
    "apply now",
    "career opportunity",
]
```

---

## 八、调试流程

发现主列表有不相关文章时，按这个顺序排查：

```
1. 看文章标题 → 找到触发匹配的词
2. 确认是哪家公司的 alias 命中了
3. 噪声是 title 命中还是 description 命中？
   - description 命中 + 公司是 strict_title_match=False → 改 strict_title_match=True
                                                         或补 excluded_noise_terms
   - title 命中 → 直接补 excluded_noise_terms（精确词组）
4. 改完后重启后端，触发 force_refresh
5. 验证该条目消失
```
