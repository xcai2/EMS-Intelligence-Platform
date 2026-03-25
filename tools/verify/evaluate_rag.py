#!/usr/bin/env python3
"""
RAG system accuracy evaluation against ground truth CapEx values.

Usage:
    python tools/verify/evaluate_rag.py [--output results.csv]

Reads groundtruth.xlsx, queries the RAG backend for each entry,
extracts the CapEx value, and reports accuracy.
"""
import re
import sys
import json
import time
import argparse
import requests
import openpyxl
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BACKEND_URL = "http://localhost:8001"
GROUND_TRUTH_PATH = Path(__file__).parent / "groundtruth.xlsx"

# Map ground-truth company names → company_filter sent to API
COMPANY_FILTER_MAP = {
    "Flex": "Flex",
    "Jabil": "Jabil",
    "Celestica": "Celestica",
    "Sanmina": "Sanmina",
    "Benchmark": "Benchmark",
}


# ---------------------------------------------------------------------------
# Query builder
# ---------------------------------------------------------------------------
def build_query(company: str, fiscal_year: int, quarter: Optional[int]) -> str:
    if quarter:
        return (
            f"what is the capex of {company} in Q{quarter} {fiscal_year}?"
        )
    else:
        return (
            f"what is the capex of {company} in {fiscal_year}?"
        )


# ---------------------------------------------------------------------------
# Value extractor
# ---------------------------------------------------------------------------
def extract_capex_value(text: str) -> Optional[float]:
    """
    Extract CapEx value in millions from LLM response text.
    Handles: $530M, $530 million, 530 million, $147,357 thousand → 147.357M,
    $1.2 billion → 1200M, parenthetical negatives (530) → 530.
    Returns value in millions, or None if not found.
    """
    # Normalize parenthetical negatives: (530) → 530
    text = re.sub(r'\(([0-9,]+(?:\.[0-9]+)?)\)', r'\1', text)

    # Ordered patterns: (regex, multiplier_to_millions)
    patterns = [
        # Billions first (avoid false match on smaller numbers)
        (r'\$\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:billion|bn|B)\b', 1_000),
        (r'\b([0-9,]+(?:\.[0-9]+)?)\s*billion\b', 1_000),
        # Millions
        (r'\$\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:million|M|mn)\b', 1),
        (r'\b([0-9,]+(?:\.[0-9]+)?)\s*million\b', 1),
        # Thousands
        (r'\$\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:thousand|K|k)\b', 0.001),
        (r'\b([0-9,]+(?:\.[0-9]+)?)\s*thousand\b', 0.001),
    ]

    for pattern, multiplier in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            val_str = m.group(1).replace(',', '')
            return round(abs(float(val_str)) * multiplier, 3)

    return None


# ---------------------------------------------------------------------------
# API caller
# ---------------------------------------------------------------------------
def query_rag(query: str, company: str) -> dict:
    company_filter = COMPANY_FILTER_MAP.get(company, company)
    payload = {
        "query": query,
        "mode": "rag",
        "company_filter": company_filter,
        "use_reranking": True,
    }
    try:
        resp = requests.post(
            f"{BACKEND_URL}/api/chat",
            json=payload,
            timeout=90,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        return {"error": "timeout", "response": ""}
    except Exception as e:
        return {"error": str(e), "response": ""}


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------
def compare(actual: Optional[float], expected: float, tolerance: float = 0.05) -> dict:
    if actual is None or expected is None:
        return {
            "exact_match": False,
            "within_tolerance": False,
            "error_pct": None,
            "actual": actual,
            "expected": expected,
        }
    if expected == 0:
        exact = actual == 0
        return {
            "exact_match": exact,
            "within_tolerance": exact,
            "error_pct": 0.0 if exact else 100.0,
            "actual": actual,
            "expected": expected,
        }
    error_pct = abs(actual - expected) / abs(expected)
    return {
        "exact_match": abs(actual - expected) < 0.1,
        "within_tolerance": error_pct <= tolerance,
        "error_pct": round(error_pct * 100, 2),
        "actual": actual,
        "expected": expected,
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def print_report(results: list[dict]):
    total = len(results)
    if total == 0:
        print("No results.")
        return

    exact = sum(1 for r in results if r.get("exact_match"))
    within_5 = sum(1 for r in results if r.get("within_tolerance"))
    no_answer = sum(1 for r in results if r.get("actual") is None)
    wrong = total - within_5 - no_answer

    print(f"\n{'=' * 70}")
    print(f"  RAG CapEx Accuracy Report")
    print(f"{'=' * 70}")
    print(f"  Total questions:     {total}")
    print(f"  Within 5% tolerance: {within_5}/{total}  ({within_5/total*100:.1f}%)")
    print(f"  Exact match (<0.1M): {exact}/{total}  ({exact/total*100:.1f}%)")
    print(f"  No value extracted:  {no_answer}")
    print(f"  Wrong value:         {wrong}")
    print(f"{'=' * 70}")

    # Per-company summary
    companies = sorted({r["company"] for r in results})
    print(f"\n  Per-company breakdown:")
    for co in companies:
        co_results = [r for r in results if r["company"] == co]
        co_pass = sum(1 for r in co_results if r.get("within_tolerance"))
        print(f"    {co:<12} {co_pass}/{len(co_results)} passed")

    # Detail table
    print(f"\n  {'Label':<28} {'Expected':>10} {'Extracted':>10} {'Error%':>8}  Status")
    print(f"  {'-'*65}")
    for r in results:
        label = r.get("label", "?")[:27]
        expected = f"${r['expected']:.1f}M" if r.get("expected") is not None else "N/A"
        actual = f"${r['actual']:.1f}M" if r.get("actual") is not None else "---"
        err = f"{r['error_pct']:.1f}%" if r.get("error_pct") is not None else "N/A"
        status = "PASS" if r.get("within_tolerance") else ("NO_ANS" if r.get("actual") is None else "FAIL")
        print(f"  {label:<28} {expected:>10} {actual:>10} {err:>8}  {status}")
    print()


def export_csv(results: list[dict], output_path: str):
    import csv
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["label", "filename", "company", "fiscal_year", "quarter",
              "expected", "actual", "error_pct", "exact_match", "within_tolerance",
              "response_snippet"]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    print(f"  Results exported to {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Evaluate RAG CapEx accuracy")
    parser.add_argument("--output", default="", help="Optional CSV output path")
    parser.add_argument("--company", default="", help="Filter to one company")
    parser.add_argument("--delay", type=float, default=1.5,
                        help="Seconds to wait between API calls (default 1.5)")
    args = parser.parse_args()

    # Health check
    try:
        r = requests.get(f"{BACKEND_URL}/api/health", timeout=5)
        if r.status_code != 200:
            print(f"Backend not healthy: {r.status_code}")
            sys.exit(1)
        print(f"Backend OK: {BACKEND_URL}")
    except Exception as e:
        print(f"Cannot reach backend at {BACKEND_URL}: {e}")
        sys.exit(1)

    # Load ground truth
    wb = openpyxl.load_workbook(GROUND_TRUTH_PATH)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]
    data_rows = rows[1:]

    # Filter by company if requested
    if args.company:
        data_rows = [r for r in data_rows if r[1] and args.company.lower() in r[1].lower()]

    print(f"Evaluating {len(data_rows)} entries...\n")

    results = []
    for i, row in enumerate(data_rows, 1):
        filename, company, fiscal_year, quarter, expected_capex, page_num, notes = row

        # Skip rows that don't have a numeric expected_capex yet
        if expected_capex is None:
            print(f"[{i}/{len(data_rows)}] Skipping row with empty expected_capex for company={company}, year={fiscal_year}, quarter={quarter}")
            continue

        fiscal_year = int(fiscal_year)
        quarter = int(quarter) if quarter else None
        label = f"{company} FY{fiscal_year}" + (f" Q{quarter}" if quarter else "")

        query = build_query(company, fiscal_year, quarter)
        print(f"[{i}/{len(data_rows)}] {label}")
        print(f"  Query:    {query}")

        api_result = query_rag(query, company)
        if api_result.get("error"):
            print(f"  ERROR:    {api_result['error']}")
            response_text = ""
        else:
            response_text = api_result.get("response", "")

        actual_capex = extract_capex_value(response_text)
        cmp = compare(actual_capex, expected_capex)

        result = {
            "label": label,
            "filename": filename,
            "company": company,
            "fiscal_year": fiscal_year,
            "quarter": quarter,
            "expected": expected_capex,
            "actual": actual_capex,
            "error_pct": cmp["error_pct"],
            "exact_match": cmp["exact_match"],
            "within_tolerance": cmp["within_tolerance"],
            "response_snippet": response_text[:300].replace("\n", " "),
        }
        results.append(result)

        status = "✓ PASS" if cmp["within_tolerance"] else ("? NO_ANS" if actual_capex is None else "✗ FAIL")
        print(f"  Expected: ${expected_capex}M | Extracted: {'$'+str(actual_capex)+'M' if actual_capex else 'None'} | {status}")
        if response_text:
            preview = response_text[:200].replace("\n", " ")
            print(f"  Response: {preview}")
        print()

        if i < len(data_rows):
            time.sleep(args.delay)

    print_report(results)

    if args.output:
        export_csv(results, args.output)


if __name__ == "__main__":
    main()
