#!/usr/bin/env python3
"""
Initialize or regenerate a minimal groundtruth.xlsx focused on Benchmark.

This creates tools/verify/groundtruth.xlsx with the header expected by
tools/verify/evaluate_rag.py and adds one row per Benchmark 10-K / 10-Q PDF.

Columns:
    filename, company, fiscal_year, quarter, expected_capex, page_num, notes

expected_capex is left empty (None) so you can fill the true values manually
from the PDFs. evaluate_rag.py has been updated to skip rows where
expected_capex is empty, so it is safe to run evaluation before all values
are filled.

Usage:
    cd Flex-Practicum-Project-2026
    python tools/verify/init_groundtruth_benchmark.py
"""

from pathlib import Path

import openpyxl


PROJECT_ROOT = Path(__file__).resolve().parents[2]
VERIFY_DIR = PROJECT_ROOT / "tools" / "verify"
GROUNDTRUTH_PATH = VERIFY_DIR / "groundtruth.xlsx"


# Benchmark filings to include in ground truth template.
# (filename, fiscal_year, quarter_or_None)
BENCHMARK_FILINGS = [
    # 10-K annual reports
    ("2022_Benchmark_10K.pdf", 2022, None),
    ("2023_Benchmark_10K.pdf", 2023, None),
    ("2024_Benchmark_10K.pdf", 2024, None),
    ("2025_Benchmark_10K.pdf", 2025, None),
    # 10-Q quarterly reports
    ("2022_Q1_Benchmark_10Q.pdf", 2022, 1),
    ("2022_Q2_Benchmark_10Q.pdf", 2022, 2),
    ("2022_Q3_Benchmark_10Q.pdf", 2022, 3),
    ("2023_Q1_Benchmark_10Q.pdf", 2023, 1),
    ("2023_Q2_Benchmark_10Q.pdf", 3, 2),
    ("2023_Q3_Benchmark_10Q.pdf", 2023, 3),
    ("2024_Q1_Benchmark_10Q.pdf", 2024, 1),
    ("2024_Q2_Benchmark_10Q.pdf", 2024, 2),
    ("2024_Q3_Benchmark_10Q.pdf", 2024, 3),
    ("2025_Q1_Benchmark_10Q.pdf", 2025, 1),
    ("2025_Q2_Benchmark_10Q.pdf", 2025, 2),
    ("2025_Q3_Benchmark_10Q.pdf", 2025, 3),
]


def main() -> None:
    VERIFY_DIR.mkdir(parents=True, exist_ok=True)

    if GROUNDTRUTH_PATH.exists():
        print(f"⚠️  {GROUNDTRUTH_PATH} already exists.")
        print("    This script will OVERWRITE it with a fresh Benchmark-only template.")
        GROUNDTRUTH_PATH.unlink()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "groundtruth"

    # Header expected by evaluate_rag.py
    header = ["filename", "company", "fiscal_year", "quarter", "expected_capex", "page_num", "notes"]
    ws.append(header)

    for filename, fy, q in BENCHMARK_FILINGS:
        ws.append(
            [
                filename,          # filename
                "Benchmark",       # company
                fy,                # fiscal_year
                q,                 # quarter (None for annual)
                None,              # expected_capex (to be filled manually, in millions)
                None,              # page_num (optional)
                "",                # notes
            ]
        )

    wb.save(GROUNDTRUTH_PATH)
    print(f"✅  Wrote Benchmark ground truth template to {GROUNDTRUTH_PATH}")
    print("    Please open it in Excel and fill 'expected_capex' (in millions)")
    print("    before running: python tools/verify/evaluate_rag.py --company Benchmark")


if __name__ == "__main__":
    main()

