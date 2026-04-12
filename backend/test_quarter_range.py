"""
测试 quarter range 相关功能是否正常工作。
运行方式: python test_quarter_range.py
"""
import re
from datetime import date
from typing import Optional

# 直接复制函数，不依赖 backend 模块
COMPANY_FY_START = {
    "Flex":      4,
    "Jabil":     9,
    "Celestica": 1,
    "Benchmark": 1,
    "Sanmina":  10,
}

_QUARTER_COUNT_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6,
    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6,
}


def _extract_quarter_range(query: str) -> Optional[int]:
    q_lower = query.lower()
    pattern = r'\b(?:last|past|previous|prior|recent)\s+(\w+)\s+quarters?\b'
    match = re.search(pattern, q_lower)
    if match:
        word = match.group(1)
        count = _QUARTER_COUNT_WORDS.get(word)
        if count:
            return count
    digit_match = re.search(
        r'\b(?:last|past|previous|prior|recent)\s+(\d+)\s+quarters?\b', q_lower
    )
    if digit_match:
        count = int(digit_match.group(1))
        if 1 <= count <= 12:
            return count
    if re.search(
        r'\b(?:last|past|previous|prior|recent)\s+(?:few|several|some|multiple)\s+quarters?\b',
        q_lower
    ):
        return 3
    if re.search(r'\b(?:last|past|previous|prior|recent)\s+quarter\b', q_lower):
        return 1
    return None


def _extract_explicit_periods(query: str) -> list[tuple[str, str]]:
    q_lower = query.lower()
    periods = []
    m = re.search(
        r'\bfy\s*(\d{2,4})\s+q([1-4])\s*(?:to|through|-)\s*q([1-4])\b', q_lower
    )
    if m:
        year = m.group(1)
        year = f"20{year}" if len(year) == 2 else year
        start_q = int(m.group(2))
        end_q = int(m.group(3))
        for q in range(start_q, end_q + 1):
            periods.append((year, f"Q{q}"))
        return periods
    m2 = re.search(r'\bq([1-4])\s*(?:to|through|-)\s*q([1-4])\b', q_lower)
    if m2:
        start_q = int(m2.group(1))
        end_q = int(m2.group(2))
        if end_q >= start_q:
            for q in range(start_q, end_q + 1):
                periods.append(("", f"Q{q}"))
            return periods
    # 只有一个 FY 时才走这里，多个 FY 留给模式4处理
    all_years = re.findall(r'\bfy\s*(\d{2,4})\b', q_lower)
    q_matches = re.findall(r'\bq([1-4])\b', q_lower)
    if len(all_years) == 1 and q_matches:
        year = all_years[0]
        year = f"20{year}" if len(year) == 2 else year
        for q in q_matches:
            p = (year, f"Q{q}")
            if p not in periods:
                periods.append(p)
        return periods
    # 先找所有 FY+year 的位置，再找紧跟其后的 Q
    cross_matches = re.findall(r'\bfy\s*(\d{2,4})\b[^fy]*?\bq([1-4])\b', q_lower)
    if len(cross_matches) >= 2:
        for year, q in cross_matches:
            year = f"20{year}" if len(year) == 2 else year
            p = (year, f"Q{q}")
            if p not in periods:
                periods.append(p)
        return periods
    return periods


def _extract_quarters_ago(query: str, company: str = None) -> list[tuple[str, str]]:
    """
    解析 "N quarters ago" 类型的相对时间表达。
    返回那一个特定季度的 (fiscal_year, quarter)。
    """
    q_lower = query.lower()

    pattern = r'\b(\w+)\s+quarters?\s+ago\b'
    match = re.search(pattern, q_lower)
    if not match:
        return []

    word = match.group(1)
    count = _QUARTER_COUNT_WORDS.get(word)
    if not count:
        return []

    today = date.today()
    fy_start = COMPANY_FY_START.get(company, 1) if company else 1

    month = today.month
    year = today.year

    month -= 3
    if month <= 0:
        month += 12
        year -= 1

    for _ in range(count - 1):
        month -= 3
        if month <= 0:
            month += 12
            year -= 1

    fy_month = (month - fy_start) % 12
    q_num = fy_month // 3 + 1
    fy_year = year - 1 if month < fy_start else year

    return [(str(fy_year), f"Q{q_num}")]


def _get_recent_fiscal_periods(n_quarters: int, company: str = None) -> list[tuple[str, str]]:
    today = date.today()
    fy_start = COMPANY_FY_START.get(company, 1) if company else 1
    periods = []
    year = today.year
    month = today.month
    for _ in range(n_quarters + 1):
        fy_month = (month - fy_start) % 12
        q_num = fy_month // 3 + 1
        fy_year = year - 1 if month < fy_start else year
        periods.append((str(fy_year), f"Q{q_num}"))
        month -= 3
        if month <= 0:
            month += 12
            year -= 1
    seen = []
    for p in periods:
        if p not in seen:
            seen.append(p)
    return seen[1:n_quarters + 1]


def _build_quarter_range_note(n_quarters: int, company: str = None) -> str:
    today = date.today()
    fy_start = COMPANY_FY_START.get(company, 1) if company else 1
    month = today.month
    year = today.year
    fy_month = (month - fy_start) % 12
    q_num = fy_month // 3 + 1
    fy_year = year - 1 if month < fy_start else year
    current_fy = str(fy_year)
    current_q = f"Q{q_num}"
    target_periods = _get_recent_fiscal_periods(n_quarters, company)
    periods_str = ", ".join(f"FY{fy} {q}" for fy, q in target_periods)
    return (
        f"[TIME RANGE NOTE] The current quarter (FY{current_fy} {current_q}) "
        f"is still in progress and has been excluded. "
        f"The following data covers the last {n_quarters} completed quarter(s): "
        f"{periods_str}."
    )

# ============================================================
# 测试1: _extract_quarter_range 变体说法识别
# ============================================================
print("=" * 50)
print("测试1: _extract_quarter_range")
print("=" * 50)

cases = [
    # 标准写法
    ("last three quarters",         3),
    ("last 3 quarters",             3),
    ("past four quarters",          4),
    ("previous 2 quarters",         2),
    # recent 变体
    ("recent 3 quarters",           3),
    ("recent quarter",              1),
    # few/several 变体
    ("last few quarters",           3),
    ("last several quarters",       3),
    # 单数
    ("last quarter",                1),
    ("past quarter",                1),
    # 无关问题
    ("what is Flex revenue",        None),
    ("compare all companies",       None),
]

all_pass = True
for query, expected in cases:
    result = _extract_quarter_range(query)
    status = "✅" if result == expected else "❌"
    if result != expected:
        all_pass = False
    print(f"  {status} '{query}' -> {result} (expected {expected})")

print(f"\n测试1结果: {'全部通过 ✅' if all_pass else '有失败 ❌'}\n")


# ============================================================
# 测试2: _extract_explicit_periods 指定季度范围
# ============================================================
print("=" * 50)
print("测试2: _extract_explicit_periods")
print("=" * 50)

explicit_cases = [
    ("FY2025 Q1 to Q3",         [("2025","Q1"),("2025","Q2"),("2025","Q3")]),
    ("FY25 Q1 to Q3",           [("2025","Q1"),("2025","Q2"),("2025","Q3")]),
    ("Q1 to Q3",                [("","Q1"),("","Q2"),("","Q3")]),
    ("Q1-Q3",                   [("","Q1"),("","Q2"),("","Q3")]),
    ("Q1 through Q3",           [("","Q1"),("","Q2"),("","Q3")]),
    ("FY2024 Q1, Q2, Q3",       [("2024","Q1"),("2024","Q2"),("2024","Q3")]),
    ("Q2 and Q3 FY2024",        [("2024","Q2"),("2024","Q3")]),
    ("FY24 Q3 and FY25 Q1",     [("2024","Q3"),("2025","Q1")]),
    # 无关问题
    ("last three quarters",     []),
    ("what is Flex revenue",    []),
]

all_pass = True
for query, expected in explicit_cases:
    result = _extract_explicit_periods(query)
    status = "✅" if result == expected else "❌"
    if result != expected:
        all_pass = False
    print(f"  {status} '{query}'")
    if result != expected:
        print(f"      got:      {result}")
        print(f"      expected: {expected}")

print(f"\n测试2结果: {'全部通过 ✅' if all_pass else '有失败 ❌'}\n")


# ============================================================
# 测试3: _get_recent_fiscal_periods 今天日期倒推
# ============================================================
print("=" * 50)
print("测试3: _get_recent_fiscal_periods")
print("=" * 50)

today = date.today()
print(f"  今天日期: {today}")
print()

for company in ["Flex", "Jabil", "Celestica", "Benchmark", "Sanmina"]:
    fy_start = COMPANY_FY_START[company]
    periods = _get_recent_fiscal_periods(3, company)
    print(f"  {company} (FY起始月={fy_start}月) 过去3个季度:")
    for fy, q in periods:
        print(f"    FY{fy} {q}")
    print()

# 无公司（自然年）
periods = _get_recent_fiscal_periods(3, None)
print(f"  无公司（自然年）过去3个季度:")
for fy, q in periods:
    print(f"    FY{fy} {q}")
print()


# ============================================================
# 测试4: _build_quarter_range_note 提示信息
# ============================================================
print("=" * 50)
print("测试4: _build_quarter_range_note")
print("=" * 50)

for company in ["Flex", "Jabil", None]:
    note = _build_quarter_range_note(3, company)
    label = company if company else "无公司"
    print(f"  [{label}]")
    print(f"  {note}")
    print()


# ============================================================
# 测试5: 优先级验证（explicit > n_quarters > latest）
# ============================================================
print("=" * 50)
print("测试5: 优先级验证")
print("=" * 50)

priority_cases = [
    # explicit 优先
    ("FY2025 Q1 to Q3",     "explicit",    True,  False),
    # n_quarters 其次
    ("last three quarters", "n_quarters",  False, True),
    # 两者都无
    ("what is revenue",     "none",        False, False),
]

for query, expected_type, has_explicit, has_nq in priority_cases:
    explicit = _extract_explicit_periods(query)
    nq = _extract_quarter_range(query)

    if explicit:
        actual_type = "explicit"
    elif nq is not None:
        actual_type = "n_quarters"
    else:
        actual_type = "none"

    status = "✅" if actual_type == expected_type else "❌"
    print(f"  {status} '{query}' -> {actual_type} (expected {expected_type})")

print()

# ============================================================
# 测试6: _extract_quarters_ago 相对时间表达
# ============================================================
print("=" * 50)
print("测试6: _extract_quarters_ago")
print("=" * 50)

print(f"  今天日期: {date.today()}")
print()

ago_cases = [
    "two quarters ago",
    "3 quarters ago",
    "one quarter ago",
    "four quarters ago",
    # 无关问题
    "last three quarters",
    "what is Flex revenue",
]

for query in ago_cases:
    result = _extract_quarters_ago(query, "Jabil")
    print(f"  '{query}' -> {result}")

print()
print("=" * 50)
print("所有测试完成")
print("=" * 50)
