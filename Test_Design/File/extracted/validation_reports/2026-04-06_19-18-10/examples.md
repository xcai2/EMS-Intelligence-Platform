# 质量问题样本摘录

以下为各检查项中检测到的问题样例，供人工快速确认。

---

## 页眉/页脚污染样本

**`Flex_8-K_2022-01-26.html.parsed.json`** (得分 0.00)
  - '104'
  - 'FLEX LTD.'

---

## 目录 (TOC) 污染样本

_该检查项未发现问题样本。_

---

## 残句截断样本

**`02.-Flex_EP_FY22Q4.pdf.parsed.json`** (得分 0.21)
  - '...h\nSolutions\nIndustrial\nCEC\nLifestyle\nConsumer\nDevicesKey markets\ndriving outsized\ngrowthInvesting in high-growth markets'
  - '...pipeline remains healthy\n•Headwinds with US module supply (anti-dumping investigation) and component shortagesNEXTRACKER'
  - '...rentiated capabilities\nprovide significant value for our customersFlex’s competitive advantages\nbolster our right to win'
  - '...j. SG&A\n% of Revenue\n$1,760$1,9577.3%7.5%\nF21 F22Adj. Gross Profit\nSee Appendix for GAAP to Non -GAAP reconciliation. 16'

**`2025_Flex_10K.parsed.json`** (得分 1.00)
  - '...quare feet in facilities that we own with the remaining 25.8 million square feet in leased facilities. Table of Contents'
  - '...were available to be repurchased under the current plan. RECENT SALES OF UNREGISTERED SECURITIES None. Table of Contents'
  - '...ue, it could result in material impairments of our goodwill. Refer to note 2 to the consolidated financial statements in'
  - '...tements in Item 8, "Financial Statements and Supplementary Data" for recent accounting pronouncements. Table of Contents'

**`2025_Q2_Flex_10Q.parsed.json`** (得分 1.00)
  - '... Officer (Principal Executive Officer) /s/ KEVIN KRUMM Kevin Krumm Chief Financial Officer (Principal Financial Officer)'

**`FLEX_PR_26Q1.pdf.parsed.json`** (得分 0.50)
  - '...ck-based compensation expense, $0.15 for net intangible amortization and $0.09 for net restructuring &amp; other charges'
  - '...s Yvette Lorenz Director, Executive Communications and Corporate PR (415) 225-7315 Yvette.Lorenz@flex.com\n<!-- image -->'
  - 'FLEX UNAUDITED CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS'
  - '...P financial measures. See the accompanying notes on Schedule V attached to this press release.\nSCHEDULE I\n<!-- image -->'

**`Flex_8-K_2022-01-26.html.parsed.json`** (得分 0.66)
  - '...ess release, dated January 26, 2022, issued by Flex Ltd.\n104\nCover Page Interactive Data File (formatted as Inline XBRL)'
  - '...rized.\nFLEX LTD.\nDate: January 26, 2022\nBy:\n/s/ Paul R. Lundstrom\nName:\nPaul R. Lundstrom\nTitle:\nChief Financial Officer'

**`flex_2024_10_17_crown_acquisition.md.parsed.json`** (得分 0.26)
  - '...\n**CapEx Related:** Yes ($325M acquisition investment)\n**AI Related:** Yes (data center power infrastructure for AI)\n---'
  - '...le challenges in the data center space. The transaction is expected to be accretive in the first year after closure.\n---'
  - '...Approximately $120 million\n- **EBITDA Margin:** High-teens (17-19%)\n- **Strong profitability and growth trajectory**\n---'
  - '...cation)\n- Canada\n**Customer Base:**\n- Utilities\n- Data centers\n- Power generation\n- Long-standing customer relationships'

---

## Chunk 重复样本

**`2025_Flex_10K.parsed.json`** (得分 0.74)
  - Chunk [83, 84] · Jaccard 相似度: **0.508**
    - A: `(a) Evaluation of Disclosure Controls and Procedures The Company's management, w...`
    - B: `over financial reporting that occurred during the fourth quarter ended March 31,...`
  - Chunk [87, 88] · Jaccard 相似度: **1.0**
    - A: `Information with respect to this item may be found in the Company's definitive p...`
    - B: `Information with respect to this item may be found in the Company's definitive p...`
  - Chunk [88, 89] · Jaccard 相似度: **0.893**
    - A: `Information with respect to this item may be found in the Company's definitive p...`
    - B: `RELATED SHAREHOLDER MATTERS Information with respect to this item may be found i...`
  - Chunk [89, 90] · Jaccard 相似度: **0.862**
    - A: `RELATED SHAREHOLDER MATTERS Information with respect to this item may be found i...`
    - B: `INDEPENDENCE Information with respect to this item may be found in the Company's...`

---
