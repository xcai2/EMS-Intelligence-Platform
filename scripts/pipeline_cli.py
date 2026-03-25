#!/usr/bin/env python3
"""
RAG Pipeline CLI - Reproducible, Stage-by-Stage Pipeline

Inspired by RAG-Challenge-2's modular pipeline approach:
- Each stage outputs artifacts to disk (can be reused)
- Can skip previous stages if artifacts exist
- Easy to debug, tune, and compare configurations

Usage:
    python scripts/pipeline_cli.py --help
    python scripts/pipeline_cli.py download-filings
    python scripts/pipeline_cli.py parse-documents
    python scripts/pipeline_cli.py build-index
    python scripts/pipeline_cli.py run-query "What was Flex's CapEx in FY24?"
    python scripts/pipeline_cli.py evaluate --questions questions.json
    python scripts/pipeline_cli.py full-pipeline  # Run everything

Pipeline Stages:
┌─────────────────────────────────────────────────────────────┐
│ 1. download-filings   │ Fetch SEC filings from EDGAR       │
│ 2. parse-documents    │ Extract text, tables, structure    │
│ 3. build-index        │ Create ChromaDB vector index       │
│ 4. run-query          │ Execute single query               │
│ 5. evaluate           │ Batch evaluation with metrics      │
│ 6. full-pipeline      │ Run all stages sequentially        │
└─────────────────────────────────────────────────────────────┘
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# ARTIFACT PATHS
# ---------------------------------------------------------------------------

ARTIFACTS_DIR = PROJECT_ROOT / "pipeline_artifacts"
FILINGS_DIR = PROJECT_ROOT / "data"
PARSED_DIR = ARTIFACTS_DIR / "parsed_documents"
INDEX_DIR = PROJECT_ROOT / "chromadb_data"
RESULTS_DIR = ARTIFACTS_DIR / "results"
LOGS_DIR = ARTIFACTS_DIR / "logs"


def ensure_dirs():
    """Create artifact directories if they don't exist."""
    for d in [ARTIFACTS_DIR, PARSED_DIR, RESULTS_DIR, LOGS_DIR]:
        d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# STAGE 1: DOWNLOAD FILINGS
# ---------------------------------------------------------------------------

def stage_download_filings(args):
    """Download SEC filings from EDGAR."""
    print("\n" + "="*60)
    print("STAGE 1: DOWNLOAD FILINGS")
    print("="*60)
    
    from backend.core.config import COMPANIES
    
    if args.company:
        companies = [args.company]
    else:
        companies = list(COMPANIES.keys())
    
    print(f"Companies to download: {companies}")
    print(f"Filing types: {args.filing_types or ['10-K', '10-Q']}")
    
    try:
        from backend.scraping.sec_scraper import SECScraper
        scraper = SECScraper()
        
        for company in companies:
            print(f"\n→ Downloading filings for {company}...")
            try:
                filings = scraper.fetch_filings(
                    company,
                    filing_types=args.filing_types or ["10-K", "10-Q"],
                    count=args.count or 8,
                )
                print(f"  ✓ Downloaded {len(filings)} filings")
            except Exception as e:
                print(f"  ✗ Error: {e}")
        
        print("\n✓ Download stage complete")
        return True
        
    except ImportError:
        print("⚠️ SEC scraper not available. Checking for existing files...")
        
        # Check existing files
        if FILINGS_DIR.exists():
            file_count = len(list(FILINGS_DIR.rglob("*.*")))
            print(f"  Found {file_count} existing files in {FILINGS_DIR}")
            return True
        else:
            print("  No existing filings found")
            return False


# ---------------------------------------------------------------------------
# STAGE 2: PARSE DOCUMENTS
# ---------------------------------------------------------------------------

def stage_parse_documents(args):
    """Parse documents and extract structured content."""
    print("\n" + "="*60)
    print("STAGE 2: PARSE DOCUMENTS")
    print("="*60)
    
    ensure_dirs()
    
    # Find all documents
    extensions = ["*.pdf", "*.html", "*.htm", "*.txt", "*.md"]
    all_files = []
    
    for ext in extensions:
        all_files.extend(list(FILINGS_DIR.rglob(ext)))
    
    print(f"Found {len(all_files)} documents to parse")
    
    if not all_files:
        print("⚠️ No documents found. Run download-filings first.")
        return False
    
    # Parse each document
    parsed_count = 0
    error_count = 0
    
    for filepath in all_files:
        output_path = PARSED_DIR / f"{filepath.stem}.json"
        
        # Skip if already parsed (unless --force)
        if output_path.exists() and not args.force:
            parsed_count += 1
            continue
        
        try:
            parsed_data = parse_document(filepath)
            
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(parsed_data, f, indent=2, ensure_ascii=False)
            
            parsed_count += 1
            
            if args.verbose:
                print(f"  ✓ Parsed: {filepath.name}")
            
        except Exception as e:
            error_count += 1
            if args.verbose:
                print(f"  ✗ Error parsing {filepath.name}: {e}")
    
    print(f"\n✓ Parsed {parsed_count} documents ({error_count} errors)")
    
    # Save parsing summary
    summary = {
        "timestamp": datetime.now().isoformat(),
        "total_files": len(all_files),
        "parsed": parsed_count,
        "errors": error_count,
    }
    with open(PARSED_DIR / "_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    
    return True


def parse_document(filepath: Path) -> dict:
    """Parse a single document into structured format."""
    suffix = filepath.suffix.lower()
    
    if suffix == ".pdf":
        return parse_pdf(filepath)
    elif suffix in [".html", ".htm"]:
        return parse_html(filepath)
    elif suffix in [".txt", ".md"]:
        return parse_text(filepath)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")


def parse_pdf(filepath: Path) -> dict:
    """Parse PDF document."""
    try:
        import pdfplumber
        
        pages = []
        tables = []
        
        with pdfplumber.open(filepath) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                pages.append({
                    "page_num": page_num,
                    "text": text,
                    "char_count": len(text),
                })
                
                # Extract tables
                page_tables = page.extract_tables() or []
                for table_idx, table in enumerate(page_tables):
                    if table and len(table) > 1:
                        tables.append({
                            "page_num": page_num,
                            "table_index": table_idx,
                            "rows": table,
                            "row_count": len(table),
                        })
        
        return {
            "source": str(filepath),
            "type": "pdf",
            "page_count": len(pages),
            "pages": pages,
            "tables": tables,
            "table_count": len(tables),
        }
        
    except ImportError:
        # Fallback to PyPDF2
        from PyPDF2 import PdfReader
        
        reader = PdfReader(filepath)
        pages = []
        
        for page_num, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            pages.append({
                "page_num": page_num,
                "text": text,
                "char_count": len(text),
            })
        
        return {
            "source": str(filepath),
            "type": "pdf",
            "page_count": len(pages),
            "pages": pages,
            "tables": [],
            "table_count": 0,
        }


def parse_html(filepath: Path) -> dict:
    """Parse HTML document."""
    from bs4 import BeautifulSoup
    
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    
    soup = BeautifulSoup(content, "lxml")
    
    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.decompose()
    
    # Extract sections
    sections = []
    for header in soup.find_all(["h1", "h2", "h3", "h4"]):
        section_text = []
        for sibling in header.find_next_siblings():
            if sibling.name in ["h1", "h2", "h3", "h4"]:
                break
            section_text.append(sibling.get_text(separator=" ", strip=True))
        
        sections.append({
            "header": header.get_text(strip=True),
            "level": int(header.name[1]),
            "content": " ".join(section_text),
        })
    
    # Extract tables
    tables = []
    for table_idx, table in enumerate(soup.find_all("table")):
        rows = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if cells:
                rows.append(cells)
        
        if rows:
            tables.append({
                "table_index": table_idx,
                "rows": rows,
                "row_count": len(rows),
            })
    
    full_text = soup.get_text(separator="\n", strip=True)
    
    return {
        "source": str(filepath),
        "type": "html",
        "section_count": len(sections),
        "sections": sections,
        "tables": tables,
        "table_count": len(tables),
        "full_text": full_text[:50000],  # Limit size
    }


def parse_text(filepath: Path) -> dict:
    """Parse plain text document."""
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    
    # Simple section detection
    lines = content.split("\n")
    sections = []
    current_section = {"header": "Introduction", "content": []}
    
    for line in lines:
        if line.strip() and line.strip().isupper() and len(line.strip()) < 100:
            if current_section["content"]:
                current_section["content"] = "\n".join(current_section["content"])
                sections.append(current_section)
            current_section = {"header": line.strip(), "content": []}
        else:
            current_section["content"].append(line)
    
    if current_section["content"]:
        current_section["content"] = "\n".join(current_section["content"])
        sections.append(current_section)
    
    return {
        "source": str(filepath),
        "type": "text",
        "section_count": len(sections),
        "sections": sections,
        "char_count": len(content),
    }


# ---------------------------------------------------------------------------
# STAGE 3: BUILD INDEX
# ---------------------------------------------------------------------------

def stage_build_index(args):
    """Build ChromaDB vector index."""
    print("\n" + "="*60)
    print("STAGE 3: BUILD INDEX")
    print("="*60)
    
    try:
        # Import the build script
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
        from build_chromadb import build_db
        
        print(f"Data directory: {FILINGS_DIR}")
        print(f"Index directory: {INDEX_DIR}")
        print(f"Per-company collections: {args.per_company}")
        
        # Run the build
        start_time = time.time()
        build_db(
            data_dir=str(FILINGS_DIR),
            use_per_company=args.per_company,
        )
        elapsed = time.time() - start_time
        
        print(f"\n✓ Index built in {elapsed:.1f} seconds")
        
        # Save build info
        build_info = {
            "timestamp": datetime.now().isoformat(),
            "data_dir": str(FILINGS_DIR),
            "index_dir": str(INDEX_DIR),
            "per_company": args.per_company,
            "build_time_seconds": elapsed,
        }
        with open(INDEX_DIR / "_build_info.json", "w") as f:
            json.dump(build_info, f, indent=2)
        
        return True
        
    except Exception as e:
        print(f"✗ Error building index: {e}")
        import traceback
        traceback.print_exc()
        return False


# ---------------------------------------------------------------------------
# STAGE 4: RUN QUERY
# ---------------------------------------------------------------------------

def stage_run_query(args):
    """Run a single query through the RAG pipeline."""
    print("\n" + "="*60)
    print("STAGE 4: RUN QUERY")
    print("="*60)
    
    query = args.query
    print(f"Query: {query}")
    print(f"Strategy: {args.strategy}")
    print(f"Mode: {'assembled' if args.assembled else 'classic'}")
    
    try:
        if args.assembled:
            from backend.rag.assembled_retriever import assembled_search
            
            result = assembled_search(
                query=query,
                company=args.company,
                top_k=args.top_k,
                strategy=args.strategy,
            )
            
            print(f"\n{'='*40}")
            print("QUERY ANALYSIS")
            print(f"{'='*40}")
            analysis = result.get("analysis", {})
            print(f"  Type: {analysis.get('query_type', 'unknown')}")
            print(f"  Companies: {analysis.get('companies', [])}")
            print(f"  Comparison: {analysis.get('is_comparison', False)}")
            
            config = result.get("config_used", {})
            if config:
                print(f"\n  Config Used:")
                print(f"    top_k: {config.get('top_k')}")
                print(f"    rerank_sample: {config.get('rerank_sample_size')}")
                print(f"    strategy: {config.get('strategy')}")
            
            print(f"\n{'='*40}")
            print("RETRIEVED CONTEXT")
            print(f"{'='*40}")
            print(result.get("context", "")[:2000])
            
        else:
            from backend.rag.retriever import search_documents
            from backend.rag.generator import generate_response
            
            docs = search_documents(
                query,
                company_filter=args.company,
                n_results=args.top_k,
                use_reranking=True,
            )
            
            print(f"\nRetrieved {len(docs)} documents")
            
            # Build context
            context = "\n\n---\n\n".join([
                f"[{d.get('company')} | {d.get('fiscal_year')}]\n{d.get('content', '')[:500]}"
                for d in docs[:5]
            ])
            
            print(f"\n{'='*40}")
            print("GENERATING RESPONSE")
            print(f"{'='*40}")
            
            response = generate_response(query, context, "")
            print(response)
        
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


# ---------------------------------------------------------------------------
# STAGE 5: EVALUATE
# ---------------------------------------------------------------------------

def stage_evaluate(args):
    """Run batch evaluation with metrics."""
    print("\n" + "="*60)
    print("STAGE 5: EVALUATE")
    print("="*60)
    
    ensure_dirs()
    
    # Load questions
    questions_file = Path(args.questions)
    if not questions_file.exists():
        print(f"✗ Questions file not found: {questions_file}")
        return False
    
    with open(questions_file, "r") as f:
        questions = json.load(f)
    
    print(f"Loaded {len(questions)} questions")
    
    # Run evaluation
    from backend.rag.assembled_retriever import assembled_search
    from backend.rag.generator import generate_response
    
    results = []
    correct = 0
    
    for i, q in enumerate(questions, 1):
        query = q.get("question", q.get("query", ""))
        expected = q.get("answer", q.get("expected", ""))
        
        print(f"\n[{i}/{len(questions)}] {query[:60]}...")
        
        try:
            # Retrieve
            retrieval = assembled_search(query=query, strategy="auto")
            context = retrieval.get("context", "")
            
            # Generate
            response = generate_response(query, context, "")
            
            # Simple accuracy check (if expected answer provided)
            is_correct = False
            if expected:
                expected_lower = str(expected).lower()
                response_lower = response.lower()
                is_correct = expected_lower in response_lower
                if is_correct:
                    correct += 1
            
            results.append({
                "question": query,
                "expected": expected,
                "response": response,
                "is_correct": is_correct,
                "analysis": retrieval.get("analysis", {}),
            })
            
        except Exception as e:
            results.append({
                "question": query,
                "error": str(e),
            })
    
    # Calculate metrics
    accuracy = correct / len(questions) if questions else 0
    
    print(f"\n{'='*40}")
    print("EVALUATION RESULTS")
    print(f"{'='*40}")
    print(f"Total questions: {len(questions)}")
    print(f"Correct: {correct}")
    print(f"Accuracy: {accuracy:.1%}")
    
    # Save results
    output_file = RESULTS_DIR / f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "questions_file": str(questions_file),
            "total": len(questions),
            "correct": correct,
            "accuracy": accuracy,
            "results": results,
        }, f, indent=2)
    
    print(f"\nResults saved to: {output_file}")
    
    return True


# ---------------------------------------------------------------------------
# STAGE 6: FULL PIPELINE
# ---------------------------------------------------------------------------

def stage_full_pipeline(args):
    """Run all stages sequentially."""
    print("\n" + "="*60)
    print("FULL PIPELINE")
    print("="*60)
    
    stages = [
        ("Download Filings", lambda: stage_download_filings(args)),
        ("Parse Documents", lambda: stage_parse_documents(args)),
        ("Build Index", lambda: stage_build_index(args)),
    ]
    
    for stage_name, stage_func in stages:
        print(f"\n>>> Running: {stage_name}")
        success = stage_func()
        if not success and not args.continue_on_error:
            print(f"\n✗ Pipeline stopped at: {stage_name}")
            return False
    
    print("\n" + "="*60)
    print("✓ FULL PIPELINE COMPLETE")
    print("="*60)
    
    return True


# ---------------------------------------------------------------------------
# CLI MAIN
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="RAG Pipeline CLI - Reproducible, Stage-by-Stage Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s download-filings --company FLEX
  %(prog)s parse-documents --verbose
  %(prog)s build-index --per-company
  %(prog)s run-query "What was Flex's CapEx in FY24?" --assembled
  %(prog)s evaluate --questions test_questions.json
  %(prog)s full-pipeline
        """,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Pipeline stage to run")
    
    # Stage 1: Download
    download_parser = subparsers.add_parser("download-filings", help="Download SEC filings")
    download_parser.add_argument("--company", help="Specific company ticker (e.g., FLEX)")
    download_parser.add_argument("--filing-types", nargs="+", default=["10-K", "10-Q"])
    download_parser.add_argument("--count", type=int, default=8, help="Filings per company")
    
    # Stage 2: Parse
    parse_parser = subparsers.add_parser("parse-documents", help="Parse documents")
    parse_parser.add_argument("--force", action="store_true", help="Re-parse existing")
    parse_parser.add_argument("--verbose", "-v", action="store_true")
    
    # Stage 3: Build Index
    index_parser = subparsers.add_parser("build-index", help="Build ChromaDB index")
    index_parser.add_argument("--per-company", action="store_true", default=True,
                              help="Create per-company collections")
    
    # Stage 4: Run Query
    query_parser = subparsers.add_parser("run-query", help="Run a single query")
    query_parser.add_argument("query", help="The question to ask")
    query_parser.add_argument("--company", help="Filter by company")
    query_parser.add_argument("--top-k", type=int, default=10)
    query_parser.add_argument("--strategy", default="auto",
                              choices=["auto", "vector", "bm25", "hybrid", "table"])
    query_parser.add_argument("--assembled", action="store_true", default=True,
                              help="Use AssembledRetriever (default)")
    query_parser.add_argument("--classic", dest="assembled", action="store_false",
                              help="Use classic retriever")
    
    # Stage 5: Evaluate
    eval_parser = subparsers.add_parser("evaluate", help="Batch evaluation")
    eval_parser.add_argument("--questions", required=True, help="JSON file with questions")
    
    # Stage 6: Full Pipeline
    full_parser = subparsers.add_parser("full-pipeline", help="Run all stages")
    full_parser.add_argument("--continue-on-error", action="store_true")
    full_parser.add_argument("--per-company", action="store_true", default=True)
    full_parser.add_argument("--verbose", "-v", action="store_true")
    full_parser.add_argument("--force", action="store_true")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Dispatch to stage
    stage_map = {
        "download-filings": stage_download_filings,
        "parse-documents": stage_parse_documents,
        "build-index": stage_build_index,
        "run-query": stage_run_query,
        "evaluate": stage_evaluate,
        "full-pipeline": stage_full_pipeline,
    }
    
    stage_func = stage_map.get(args.command)
    if stage_func:
        success = stage_func(args)
        sys.exit(0 if success else 1)
    else:
        print(f"Unknown command: {args.command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
