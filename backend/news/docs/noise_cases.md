# 漏网噪声案例与人工维护方法

最后更新：2026-04-10

这份文档记录已经发现的误命中案例，以及每种类型应该去哪个文件修。
遇到新的漏网内容时，先看这里找对应类型，再照着例子改。

---

## 类型一：公司 ticker 被同名品牌/人物误命中

**典型案例**

| 漏网内容 | 触发原因 |
|---|---|
| `wrestling-world.com/.../jbl-discusses-chris-jericho...` | JBL = John Bradshaw Layfield（摔角手） |
| `Bose Soundlink Flex 蓝牙音箱评测` | flex 命中 FLEX ticker |
| `ChromeOS Flex 系统更新` | flex 命中 FLEX ticker |
| `JBL Charge 5 vs JBL Flip 6 对比` | JBL 命中 Jabil ticker |

**修哪里**：
- 内容噪声（标题/描述含特定词）→ `backend/news/sources.py` → 对应公司的 `excluded_noise_terms`
- 整个域名都不相干 → `backend/news/sources.py` → 对应公司的 `excluded_domains`

**怎么改**：

```python
# 发现 JBL 摔角内容漏进来 → 在 JBL 的 excluded_noise_terms 里加
"excluded_noise_terms": [
    ...
    "aew",          # All Elite Wrestling
    "wwe",          # 摔角联盟
    "wrestling",
    "jericho",      # 摔角手 Chris Jericho
    # 新发现的摔角选手名字也加在这里
    "cm punk",
    "moxley",
],

# 发现 Bose Soundlink Flex 漏进来 → 在 FLEX 的 excluded_noise_terms 里加
"excluded_noise_terms": [
    ...
    "soundlink flex",
    "bose flex",
],
```

**注意**：词组要尽量具体。不要加 `"aew"` 如果它可能出现在真正的商业新闻标题里（比如 AEW 的融资报道）。

---

## 类型二：行业缩写歧义（EMS / CLS / 其他）

**典型案例**

| 漏网内容 | 触发原因 |
|---|---|
| `FortiClient EMS security vulnerability exploited` | EMS = Fortinet 安全产品，不是 Electronics Manufacturing Services |
| `CLS bank settlement` | CLS = 某结算银行，不是 Celestica |

**修哪里**：`backend/news/filtering.py` → `EXCLUDED_NOISE_TERMS`（全局生效）

**怎么改**：

```python
EXCLUDED_NOISE_TERMS = [
    ...
    # EMS 缩写歧义 - Fortinet 安全产品
    "forticlient",
    "fortinet ems",
    # 如果发现更多 EMS 歧义来源，继续在这里加
    "ems ambulance",
    "ems training",
]
```

**什么时候改这里而不是 sources.py**：
- 影响所有公司（不是某一家）→ 改 `filtering.py`
- 只影响特定公司 → 改 `sources.py` 对应公司的 `excluded_noise_terms`

---

## 类型三：Comparative 里混进了对比页 / 旧报告

**典型案例**

| 漏网内容 | 触发原因 |
|---|---|
| `medium.com/...flex-vs-jabil-comparison` | Medium 文章，comparison page |
| `owler.com/company/flex` | 公司数据库页，不是新闻 |
| `koalagains.com/ems-industry-2021` | 2021 年旧报告 |

**修哪里**：`backend/news/comparative_news_service.py` → `_COMPARATIVE_EXCLUDED_DOMAINS` 或 `_COMPARATIVE_MAX_AGE_DAYS`

**怎么改**：

```python
# 发现某个域名一直出现对比页而不是新闻 → 加到排除域名列表
_COMPARATIVE_EXCLUDED_DOMAINS = {
    "medium.com",
    "linkedin.com",
    "owler.com",
    # 新发现的加在这里
    "similarweb.com",
    "pitchbook.com",
}

# 如果对比新闻时效要求更严 → 缩短天数
_COMPARATIVE_MAX_AGE_DAYS = 60  # 原来是 90 天，改小
```

---

## 类型四：行业新闻里混进了无关 AI / 科技内容

**典型案例**

| 漏网内容 | 触发原因 |
|---|---|
| `Oracle APEX new release` | 含 AI 关键词触发行业过滤通过 |
| `NVIDIA GeForce driver update` | 含 nvidia 触发 AI 关键词 |

**修哪里**：`backend/news/filtering.py` → `AI_TERMS`（移除过于宽泛的词）
或 `backend/news/news_filter_policies.py` → `filter_industry_news_items`（加额外条件）

这类问题改动影响较大，改前先确认是系统性问题还是偶发。

---

## 查找漏网内容的步骤

```
1. 看文章 URL 和标题，判断属于哪个类型（上面四种之一）
2. 找到对应的修改位置
3. 加最精确的词组（避免误杀正常文章）
4. 重启后端 + force_refresh
5. 确认该条内容不再出现
6. 把这个案例记录在本文档里（日期 + 内容摘要 + 修改位置）
```

---

## 已处理案例记录

| 日期 | 内容摘要 | 修改位置 | 加入词组 |
|---|---|---|---|
| 2026-04-10 | JBL 摔角手 John Bradshaw Layfield 相关文章 | `sources.py` JBL | `"aew"`, `"wwe"`, `"wrestling"`, `"jericho"`, `"bradshaw layfield"` |
| 2026-04-10 | Bose Soundlink Flex / ChromeOS Flex / Amazon Flex 误命中 | `sources.py` FLEX | `"soundlink flex"`, `"chromeos flex"`, `"amazon flex"`, `"bonds flex"` |
| 2026-04-10 | FortiClient EMS 安全漏洞文章误命中行业新闻 | `filtering.py` | `"forticlient"`, `"fortinet ems"` |
| 2026-04-10 | Comparative 里出现 medium/owler/koalagains 等对比页 | `comparative_news_service.py` | 加入 `_COMPARATIVE_EXCLUDED_DOMAINS` + 90 天时效过滤 |
| 2026-04-10 | cureus.com 医学文章"choroid plexus mimicry..."误命中 PLXS | `sources.py` PLXS | `"choroid plexus"`, `"cardiac plexus"`, `"ventricular plexus"` |
| 2026-04-10 | chosun.com 韩文国内新闻误命中 FLEX | `sources.py` FLEX `excluded_domains` | `"chosun.com"` |
| 2026-04-10 | kalw.org SF 公共电台"Flex 篮球表演"误命中 FLEX | `sources.py` FLEX `excluded_domains` | `"kalw.org"` |
