# 财务指标关键词参考

> 由 [backend/aichat/financial_cache/intent.py](../../backend/aichat/financial_cache/intent.py) 中的 METRICS 列表自动生成。
> 修改任何一行别名都应直接编辑 intent.py，再重新生成本文档。

**覆盖**：54 个财务指标，共 191 条别名（英文 170 条 + 中文 21 条核心词）。

AI Chat 收到用户问题时会扫描每个别名（不区分大小写、子串匹配）。命中即从 SQLite 缓存查询数据，跳过 RAG。

为避免歧义，所有别名按长度降序排序匹配——更具体的短语（如 `free cash flow`）会优先于更短的（如 `cash flow`）。

---

## 损益表 (Income Statement)

| 标签 | yfinance 字段 | 别名 |
|---|---|---|
| Total Revenue | `Total Revenue` | `total revenue` / `net revenue` / `net sales` / `operating revenue` / `revenue` / `sales` / `turnover` / `top line` / `topline` / `营收` / `收入` |
| Cost of Revenue | `Cost Of Revenue` | `cost of revenue` / `cost of goods sold` / `cost of sales` / `cogs` / `成本` |
| Gross Profit | `Gross Profit` | `gross profit` / `gross income` / `gross margin` / `毛利` |
| Operating Income | `Operating Income` | `operating income` / `operating profit` / `income from operations` / `营业利润` |
| Operating Expense | `Operating Expense` | `operating expense` / `operating expenses` / `opex` |
| SG&A | `Selling General And Administration` | `selling general and administration` / `selling general administrative` / `sg&a` / `sga` / `selling and administrative` |
| EBITDA | `EBITDA` | `ebitda` / `earnings before interest taxes depreciation and amortization` |
| EBIT | `EBIT` | `ebit` / `earnings before interest and tax` |
| Pretax Income | `Pretax Income` | `pretax income` / `pre-tax income` / `pre tax income` / `income before tax` / `ebt` / `earnings before tax` |
| Income Tax | `Tax Provision` | `tax provision` / `income tax` / `income taxes` / `tax expense` |
| Interest Expense | `Interest Expense` | `interest expense` |
| Interest Income | `Interest Income` | `interest income` |
| Net Income | `Net Income` | `net income` / `net profit` / `net earnings` / `bottom line` / `bottomline` / `净利润` |
| Diluted EPS | `Diluted EPS` | `diluted earnings per share` / `diluted eps` |
| Basic EPS | `Basic EPS` | `basic earnings per share` / `basic eps` |
| Diluted EPS | `Diluted EPS` | `earnings per share` / `eps` / `每股收益` |

## 资产负债表 (Balance Sheet)

| 标签 | yfinance 字段 | 别名 |
|---|---|---|
| Total Assets | `Total Assets` | `total assets` / `总资产` |
| Total Liabilities | `Total Liabilities Net Minority Interest` | `total liabilities` |
| Net Debt | `Net Debt` | `net debt` / `净债务` |
| Total Debt | `Total Debt` | `total debt` / `总债务` |
| Long Term Debt | `Long Term Debt` | `long term debt` / `long-term debt` / `ltd` |
| Current Debt | `Current Debt` | `current debt` / `short term debt` / `short-term debt` / `std` |
| Stockholders Equity | `Stockholders Equity` | `stockholders equity` / `stockholders' equity` / `shareholders equity` / `shareholders' equity` / `book value` / `equity` / `股东权益` |
| Working Capital | `Working Capital` | `working capital` / `nwc` / `net working capital` / `营运资本` |
| Inventory | `Inventory` | `inventories` / `inventory` / `stock on hand` / `存货` |
| Receivables | `Receivables` | `accounts receivable` / `trade receivables` / `receivables` / `ar` / `应收账款` |
| Accounts Payable | `Accounts Payable` | `accounts payable` / `trade payables` / `payables` / `ap` |
| Goodwill | `Goodwill` | `goodwill` |
| Property, Plant & Equipment (Net) | `Net PPE` | `property plant and equipment` / `property, plant and equipment` / `property plant equipment` / `ppe` / `pp&e` / `fixed assets` |
| Retained Earnings | `Retained Earnings` | `retained earnings` |
| Tangible Book Value | `Tangible Book Value` | `tangible book value` / `tbv` |
| Treasury Stock | `Treasury Stock` | `treasury stock` / `treasury shares` |

## 现金流量表 (Cash Flow Statement)

| 标签 | yfinance 字段 | 别名 |
|---|---|---|
| Free Cash Flow | `Free Cash Flow` | `free cash flow` / `fcf` / `自由现金流` |
| Operating Cash Flow | `Operating Cash Flow` | `operating cash flow` / `cash from operations` / `cash flow from operations` / `ocf` / `cfo` / `经营现金流` |
| Investing Cash Flow | `Investing Cash Flow` | `investing cash flow` / `cash flow from investing` / `cfi` |
| Financing Cash Flow | `Financing Cash Flow` | `financing cash flow` / `cash flow from financing` / `cff` |
| Operating Cash Flow | `Operating Cash Flow` | `cash flow` / `现金流` |
| Capital Expenditure | `Capital Expenditure` | `capital expenditures` / `capital expenditure` / `capital spending` / `capital spend` / `capital investment` / `capex` / `资本支出` |
| Depreciation & Amortization | `Depreciation And Amortization` | `depreciation and amortization` / `depreciation & amortization` / `d&a` |
| Depreciation | `Depreciation` | `depreciation` |
| Amortization | `Amortization` | `amortization` |
| Share Repurchases | `Repurchase Of Capital Stock` | `share repurchase` / `stock repurchase` / `stock buyback` / `share buyback` / `buybacks` / `buyback` |
| Debt Issuance | `Issuance Of Debt` | `debt issuance` / `issuance of debt` |
| Debt Repayment | `Repayment Of Debt` | `debt repayment` / `repayment of debt` |
| Ending Cash Position | `End Cash Position` | `end cash position` / `ending cash position` / `ending cash balance` |

## 行情快照 (Info Snapshot)

| 标签 | yfinance 字段 | 别名 |
|---|---|---|
| Market Cap | `marketCap` | `market capitalization` / `market capitalisation` / `market cap` / `mcap` / `市值` |
| P/E (Forward) | `forwardPE` | `forward pe ratio` / `forward p/e ratio` / `forward pe` / `forward p/e` / `fwd p/e` / `fwd pe` |
| P/E (Trailing) | `trailingPE` | `trailing pe ratio` / `trailing p/e ratio` / `trailing pe` / `trailing p/e` / `ttm pe` / `ttm p/e` / `p/e ratio` / `pe ratio` / `p/e` / `p e ratio` / `pe` / `市盈率` |
| EPS (TTM) | `trailingEps` | `trailing eps` / `ttm eps` |
| EPS (Forward) | `forwardEps` | `forward eps` / `fwd eps` |
| Shares Outstanding | `sharesOutstanding` | `shares outstanding` / `share count` / `outstanding shares` / `流通股` |
| Dividend Yield | `dividendYield` | `dividend yield` |
| 52-Week High | `fiftyTwoWeekHigh` | `52 week high` / `52-week high` / `fifty two week high` |
| 52-Week Low | `fiftyTwoWeekLow` | `52 week low` / `52-week low` / `fifty two week low` |

---

## CapEx 拆分识别（特殊规则）

当查询同时包含 CapEx 关键词 (`capex` / `capital expenditure` / `资本支出`) 与下列触发词之一时，**不进入缓存查询**，直接走 RAG 文档检索（因为这类问题需要文字描述，缓存里没有）：

`breakdown` / `by category` / `by region` / `by segment` / `by area` / `by project` / `where` / `用途` / `拆分` / `分类` / `构成` / `哪些` / `花在` / `分布` / `明细` / `细分`
