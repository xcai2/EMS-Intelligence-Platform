# 质量问题样本摘录

以下为各检查项中检测到的问题样例，供人工快速确认。

---

## 原文整体对齐异常样本

**`02.-Flex_EP_FY22Q4.pdf.parsed.json`** (得分 0.93)
  - 'Fourth Quarter and Full Year Highlights RevenueAdj. Operating IncomeAdj. Net IncomeAdj. Earnings Per Share FOURTH QUARTER $6.9B $295M $244M $0.52•Record adjuste...'

**`2025_Flex_10K.parsed.json`** (得分 1.00)
  - 'OVERVIEW Flex is the advanced, end-to-end manufacturing partner of choice that helps a diverse customer base design, build, deliver and manage innovative produc...'

**`2025_Q2_Flex_10Q.parsed.json`** (得分 0.99)
  - '## UNITED STATES SECURITIES AND EXCHANGE COMMISSION Washington, D.C. 20549 Form 10-Q (Mark One) ## ☒ QUARTERLY REPORT PURSUANT TO SECTION 13 OR 15(d) OF THE SEC...'

**`FLEX_PR_26Q1.pdf.parsed.json`** (得分 0.99)
  - 'Overview  <!-- image -->  FLEX REPORTS FIRST QUARTER FISCAL 2026 RESULTS  Austin, Texas, July 24, 2025 Flex (NASDAQ: FLEX) today announced results for its first...'

**`Flex_8-K_2022-01-26.html.parsed.json`** (得分 1.00)
  - 'Item 2.02 Results of Operations and Financial Condition.  On January 26, 2022, Flex Ltd. (the “Company”) issued a press release announcing financial results for...'

**`flex_2024_10_17_crown_acquisition.md.parsed.json`** (得分 1.00)
  - 'Overview  # Flex to Acquire Crown Technical Systems for $325 Million **Date:** October 17, 2024 **Type:** Acquisition Announcement **Source:** https://investors...'

**`flex_fy24q3_transcript.pdf.parsed.json`** (得分 0.00)
  - 'Transcript'

---

## 原文锚点缺失样本

**`02.-Flex_EP_FY22Q4.pdf.parsed.json`** (得分 0.20)
  - chunk#1: 'fourth quarter and full year highlights revenueadj operating incomeadj net'
  - chunk#2: 'driving sustainable growth margin improvement and creating shareholder valueour differentiated'
  - chunk#3: 'record adjusted eps q4 fy22 financial summary 6 720 6'
  - chunk#4: '677 593 f21 f22adj free cash flow m 1 031'

**`2025_Flex_10K.parsed.json`** (得分 0.78)
  - chunk#4: 'of cooling over 3 000w as well as offering complete'
  - chunk#5: 'a part of our everyday working norms building on our'
  - chunk#9: 'table of contents our business financial condition results of operations'
  - chunk#21: 'volatile the stock market in recent years has experienced significant'

**`2025_Q2_Flex_10Q.parsed.json`** (得分 0.76)
  - chunk#2: 'we have previously audited in accordance with the standards of'
  - chunk#3: 'condensed consolidated statements of shareholders equity continued accumulated accumulated accumulated'
  - chunk#7: 'under these supplier finance programs the company pays the financial'
  - chunk#18: 'specifically we offer our customers the ability to simplify their'

**`FLEX_PR_26Q1.pdf.parsed.json`** (得分 0.48)
  - chunk#4: 'austin texas july 24 2025 flex nasdaq flex today announced'
  - chunk#8: 'revenue 6.5 billion to 6.8 billion gaap operating income 322'
  - chunk#10: 'revenue 25.9 billion to 27.1 billion gaap eps 2.27 to'
  - chunk#18: 'investors amp analysts michelle simmons senior vice president global investor'

**`Flex_8-K_2022-01-26.html.parsed.json`** (得分 0.80)
  - chunk#4: 'd exhibits exhibit no 99.1 press release dated january 26'

**`flex_2024_10_17_crown_acquisition.md.parsed.json`** (得分 0.15)
  - chunk#2: 'flex to acquire crown technical systems for 325 million date'
  - chunk#10: 'history and expertise nearly three decades solving power distribution and'
  - chunk#12: 'product portfolio modular solutions prefabricated power distribution systems medium voltage'
  - chunk#17: 'power heat and scale challenges ai data centers require massive'

---

## 关键数字不一致样本

**`02.-Flex_EP_FY22Q4.pdf.parsed.json`** (得分 0.96)
  - 0.0
  - 2984.6%
  - 4.5
  - 2954.9

**`2025_Q2_Flex_10Q.parsed.json`** (得分 0.98)
  - 5%
  - 100.0%
  - 16%
  - 9%

---

## 标题回溯异常样本

**`2025_Flex_10K.parsed.json`** (得分 0.17)
  - Item 1  BUSINESS
  - Item 1A  RISK FACTORS
  - Item 1B  UNRESOLVED STAFF COMMENTS
  - Item 1C  CYBERSECURITY

**`2025_Q2_Flex_10Q.parsed.json`** (得分 0.00)
  - Full Document

**`FLEX_PR_26Q1.pdf.parsed.json`** (得分 0.86)
  - Overview
  - Notes and Disclosures

**`flex_fy24q3_transcript.pdf.parsed.json`** (得分 0.00)
  - Transcript

---

## 页眉/页脚污染样本

**`2025_Flex_10K.parsed.json`** (得分 0.00)
  - [inline] "...ite the Company's annual reports on Form 10-K, quarterly reports on Form 10-Q, cu..."
  - [inline] '...on Form 10-K, quarterly reports on Form 10-Q, current reports on Form 8-K and am...'
  - [inline] '...ts on Form 10-Q, current reports on Form 8-K and amendments to those reports fil...'
  - [inline] "...ite the Company's annual reports on Form 10-K, quarterly reports on Form 10-Q, cu..."

**`2025_Q2_Flex_10Q.parsed.json`** (得分 0.00)
  - [inline] '...E COMMISSION Washington, D.C. 20549 Form 10-Q (Mark One) ## ☒ QUARTERLY REPORT PU...'
  - [inline] '....C. 20549 Form 10-Q (Mark One) ## ☒ QUARTERLY REPORT PURSUANT TO SECTION 13 OR 15(d) OF...'
  - [inline] "...d in the Company's Annual Report on Form 10-K. In the opinion of management, all..."
  - [inline] "...31, 2025 contained in the Company's Annual Report on Form 10-K. In the opinion of man..."

**`FLEX_PR_26Q1.pdf.parsed.json`** (得分 0.89)
  - [inline] '...in our most recent Annual Report on Form 10-K and in our subsequent filings with...'
  - [inline] '...s of Operations" in our most recent Annual Report on Form 10-K and in our subsequent...'

**`Flex_8-K_2022-01-26.html.parsed.json`** (得分 0.00)
  - [full-line] '104'
  - [full-line] 'FLEX LTD.'
  - [inline] '...Item 2.02 of this Current Report on Form 8-K and the Exhibit attached hereto sha...'

---

## 目录 (TOC) 污染样本

**`2025_Flex_10K.parsed.json`** (得分 0.00)
  - [inline] '...rdinary shares of Flex held by each Table of Contents shareholder of Flex (the "Distribut...'
  - [inline] "...to managing our business increases Table of Contents customers' competitiveness by lever..."
  - [inline] '...services, we provide manufacturing, Table of Contents customization, procurement, global...'
  - [inline] '...gy on delivering value to customers Table of Contents through a comprehensive suite of pr...'

**`2025_Q2_Flex_10Q.parsed.json`** (得分 0.00)
  - [inline] '...reporting period. Estimates are ## Table of Contents used in accounting for, among other...'
  - [inline] "...rrants' for further information. ## Table of Contents ## Disaggregation of Revenue The fo..."
  - [inline] '...itions of the underlying awards. ## Table of Contents As of September 26, 2025, approxima...'
  - [inline] '...remaining 70% due upon maturity. ## Table of Contents The weighted-average interest rate...'

---

## 残句截断样本

**`02.-Flex_EP_FY22Q4.pdf.parsed.json`** (得分 0.00)
  - '...al\nCEC\nLifestyle\nConsumer\nDevicesKey markets\ndriving outsized\ngrowthInvesting in high-growth markets || next: Record adjusted EPS Q4 FY22 Financial Summary\n$6,720\n$6,266$'
  - '...lthy\n•Headwinds with US module supply (anti-dumping investigation) and component shortagesNEXTRACKER || next: Q1 FY23 Financial Guidance\nRevenue Adj. Operating IncomeA Ad'
  - '...es\nprovide significant value for our customersFlex’s competitive advantages\nbolster our right to win || next: $505 $5028.1%\n7.3%\nQ4F21 Q4F22Adj. Gross Profit\n($M)\nAdj.Gro'
  - '...\n$1,760$1,9577.3%7.5%\nF21 F22Adj. Gross Profit\nSee Appendix for GAAP to Non -GAAP reconciliation. 16 || next: Quarter-endedQuarter-endedQuarter-endedQuarter-endedYear-end'

**`2025_Flex_10K.parsed.json`** (得分 0.50)
  - '...in material impairments of our goodwill. Refer to note 2 to the consolidated financial statements in || next: Income Taxes Our deferred income tax assets represent tempor'
  - '...Financial Statements and Supplementary Data" for recent accounting pronouncements. Table of Contents || next: INTEREST RATE RISK A portion of our exposure to market risk '
  - '... on our financial position, results of operations and cash flows in the near-term. Table of Contents || next: REPORT OF INDEPENDENT REGISTERED PUBLIC ACCOUNTING FIRM To t'
  - '... per share may not equal the total earnings per share amounts for the fiscal year. Table of Contents || next: FINANCIAL DISCLOSURE Not applicable.'

**`2025_Q2_Flex_10Q.parsed.json`** (得分 0.84)
  - '...Executive Officer) /s/ KEVIN KRUMM Kevin Krumm Chief Financial Officer (Principal Financial Officer)'

**`FLEX_PR_26Q1.pdf.parsed.json`** (得分 0.00)
  - '...n expense, $0.15 for net intangible amortization and $0.09 for net restructuring &amp; other charges || next: Notes and Disclosures'
  - '...ctor, Executive Communications and Corporate PR (415) 225-7315 Yvette.Lorenz@flex.com\n<!-- image --> || next: FLEX UNAUDITED CONDENSED CONSOLIDATED STATEMENTS OF OPERATIO'
  - '.... See the accompanying notes on Schedule V attached to this press release.\nSCHEDULE I\n<!-- image --> || next: FLEX RECONCILIATION OF GAAP TO NON-GAAP FINANCIAL MEASURES ('
  - '...FLEX RECONCILIATION OF GAAP TO NON-GAAP FINANCIAL MEASURES (In millions, except per share amounts) || next: | | Three-Month Periods Ended | Three-Month Periods Ended |\n'

**`Flex_8-K_2022-01-26.html.parsed.json`** (得分 0.00)
  - '...anuary 26, 2022, issued by Flex Ltd.\n104\nCover Page Interactive Data File (formatted as Inline XBRL) || next: SIGNATURES'
  - '...e: January 26, 2022\nBy:\n/s/ Paul R. Lundstrom\nName:\nPaul R. Lundstrom\nTitle:\nChief Financial Officer || next: The information in Item 2.02 of this Current Report on Form '

**`flex_2024_10_17_crown_acquisition.md.parsed.json`** (得分 0.00)
  - '...Yes ($325M acquisition investment)\n**AI Related:** Yes (data center power infrastructure for AI)\n--- || next: Summary'
  - '... data center space. The transaction is expected to be accretive in the first year after closure.\n--- || next: Transaction Details'
  - '...illion\n- **EBITDA Margin:** High-teens (17-19%)\n- **Strong profitability and growth trajectory**\n--- || next: Crown Technical Systems Overview'
  - '...ustomer Base:**\n- Utilities\n- Data centers\n- Power generation\n- Long-standing customer relationships || next: Core Capabilities'

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
