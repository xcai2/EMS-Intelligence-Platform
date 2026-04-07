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

**`02.-Flex_EP_FY22Q4.pdf.parsed.json`** (得分 0.67)
  - chunk#3: 'record adjusted eps q4 fy22 financial summary 6 720 6'
  - chunk#4: '677 593 f21 f22adj free cash flow m 1 031'
  - chunk#6: 'revenueaadj operating margin b y/y growth y/y growth reliability 10.6'
  - chunk#7: 'cash flow overview adjusted free cash flow m 135 219'

**`FLEX_PR_26Q1.pdf.parsed.json`** (得分 0.95)
  - chunk#18: 'investors amp analysts michelle simmons senior vice president global investor'

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

**`2025_Q2_Flex_10Q.parsed.json`** (得分 0.00)
  - Full Document

**`FLEX_PR_26Q1.pdf.parsed.json`** (得分 0.86)
  - Overview
  - Notes and Disclosures

**`flex_fy24q3_transcript.pdf.parsed.json`** (得分 0.00)
  - Transcript

---

## 页眉/页脚污染样本

**`2025_Q2_Flex_10Q.parsed.json`** (得分 0.00)
  - [inline] '...SECURITIES AND EXCHANGE COMMISSION Washington, D.C. 20549 Form 10-Q (Mark One) ## ☒ QUARTERLY REPORT PU...'
  - [inline] '...E COMMISSION Washington, D.C. 20549 Form 10-Q (Mark One) ## ☒ QUARTERLY REPORT PURSUANT TO...'
  - [inline] '....C. 20549 Form 10-Q (Mark One) ## ☒ QUARTERLY REPORT PURSUANT TO SECTION 13 OR 15(d) OF THE SECURITIES EXCHA...'

**`Flex_8-K_2022-01-26.html.parsed.json`** (得分 0.00)
  - [full-line] '104'
  - [full-line] 'FLEX LTD.'

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

**`02.-Flex_EP_FY22Q4.pdf.parsed.json`** (得分 0.47)
  - '...al\nCEC\nLifestyle\nConsumer\nDevicesKey markets\ndriving outsized\ngrowthInvesting in high-growth markets || next: Record adjusted EPS Q4 FY22 Financial Summary\n$6,720\n$6,266$'
  - '...ion of our website which includes press releases and summary financials of\nthe respective periods.20'

**`2025_Flex_10K.parsed.json`** (得分 0.54)
  - '...in material impairments of our goodwill. Refer to note 2 to the consolidated financial statements in || next: Income Taxes Our deferred income tax assets represent tempor'
  - '...Financial Statements and Supplementary Data" for recent accounting pronouncements. Table of Contents || next: INTEREST RATE RISK A portion of our exposure to market risk '
  - '... on our financial position, results of operations and cash flows in the near-term. Table of Contents || next: REPORT OF INDEPENDENT REGISTERED PUBLIC ACCOUNTING FIRM To t'
  - '...dures may deteriorate. /s/ DELOITTE & TOUCHE LLP San Jose, California May 21, 2025 Table of Contents || next: Insider Trading Arrangements During the fiscal quarter ended'

**`2025_Q2_Flex_10Q.parsed.json`** (得分 0.84)
  - '...Executive Officer) /s/ KEVIN KRUMM Kevin Krumm Chief Financial Officer (Principal Financial Officer)'

**`FLEX_PR_26Q1.pdf.parsed.json`** (得分 0.68)
  - '.... See the accompanying notes on Schedule V attached to this press release.\nSCHEDULE I\n<!-- image --> || next: FLEX RECONCILIATION OF GAAP TO NON-GAAP FINANCIAL MEASURES ('
  - '...\nSee the accompanying notes on Schedule V attached to this press release.\nSCHEDULE II\n<!-- image --> || next: FLEX UNAUDITED CONDENSED CONSOLIDATED BALANCE SHEETS (In mil'
  - '...ash and cash equivalents, end of period | $ 2,239 | $ 2,243 |\n<!-- image -->\nP R E S S R E L E A S E || next: FLEX AND SUBSIDIARIES NOTES TO SCHEDULES I and II'

**`Flex_8-K_2022-01-26.html.parsed.json`** (得分 0.43)
  - '...e: January 26, 2022\nBy:\n/s/ Paul R. Lundstrom\nName:\nPaul R. Lundstrom\nTitle:\nChief Financial Officer || next: The information in Item 2.02 of this Current Report on Form '

**`flex_2024_10_17_crown_acquisition.md.parsed.json`** (得分 0.66)
  - '...ade capabilities for large-scale data centers\n- Integrated power distribution and protection systems || next: 2. Extends into Utility Power Market'
  - '...tic customers\n- Compliance with domestic content requirements\n- Supply chain resilience and security || next: 4. Increases Exposure to Fast-Growing, Margin-Accretive Mark'
  - '... Margin-accretive acquisition\n- First-year accretive to earnings\n- $120 million revenue contribution || next: 5. Aligns with EMS + Products + Services Strategy'
  - '...- FY2026 data center revenue target: $6.5 billion (35%+ growth)\n- EMS + Products + Services strategy'

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
