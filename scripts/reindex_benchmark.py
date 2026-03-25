#!/usr/bin/env python3
"""
Targeted Benchmark re-indexing script.

Deletes the stale company_benchmark ChromaDB collection (which was built from
iXBRL HTML files and contains garbage XBRL taxonomy strings), then re-indexes
all Benchmark PDFs into a fresh company_benchmark collection.

Usage:
    cd /path/to/Flex-Practicum-Project-2026
    python3 scripts/reindex_benchmark.py
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import chromadb
from sentence_transformers import SentenceTransformer

# Import core functions from build_chromadb
from build_chromadb import (
    chunk_document_with_page_parents,
    get_fiscal_quarter,
    detect_filing_type,
    _get_company_collection_name,
)

DB_PATH = str(PROJECT_ROOT / "chromadb_store")
BENCHMARK_DIR = PROJECT_ROOT / "data" / "raw" / "Benchmark"
COMPANY = "Benchmark"

# Benchmark file sources: (subdir_path, filing_type or None for auto-detect)
BENCHMARK_SOURCES = [
    (BENCHMARK_DIR / "Benchmark_filings" / "10K",       "10-K"),
    (BENCHMARK_DIR / "Benchmark_filings" / "10Q",       "10-Q"),
    (BENCHMARK_DIR / "Annual Report",                    "10-K"),
    (BENCHMARK_DIR / "Earnings Presentation" / "2022",   "Earnings Presentation"),
    (BENCHMARK_DIR / "Earnings Presentation" / "2023",   "Earnings Presentation"),
    (BENCHMARK_DIR / "Earnings Presentation" / "2024",   "Earnings Presentation"),
    (BENCHMARK_DIR / "Earnings Presentation" / "2025",   "Earnings Presentation"),
    (BENCHMARK_DIR / "Press Release" / "2022",           "Press Release"),
    (BENCHMARK_DIR / "Press Release" / "2023",           "Press Release"),
    (BENCHMARK_DIR / "Press Release" / "2024",           "Press Release"),
    (BENCHMARK_DIR / "Press Release" / "2025",           "Press Release"),
    (BENCHMARK_DIR / "Sidoti September Small-Cap Virtual Conference", "Earnings Presentation"),
]

SUPPORTED_EXTENSIONS = (".pdf", ".html", ".htm", ".txt", ".md")


def discover_benchmark_files():
    """Discover all Benchmark files from the sources list."""
    results = []
    for subdir, ftype in BENCHMARK_SOURCES:
        if not subdir.is_dir():
            print(f"  ⚠️  Not found: {subdir.relative_to(PROJECT_ROOT)}")
            continue
        files = sorted(f for f in subdir.iterdir()
                       if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS)
        if files:
            print(f"  📂 {subdir.relative_to(BENCHMARK_DIR)}: {len(files)} files")
        for f in files:
            results.append((f, ftype))
    return results


def main():
    print("=" * 65)
    print("  BENCHMARK RE-INDEXING (PDF-based)")
    print("=" * 65)

    # 1. Connect to ChromaDB
    client = chromadb.PersistentClient(path=DB_PATH)
    col_name = _get_company_collection_name(COMPANY)

    # 2. Delete old collection
    try:
        client.delete_collection(name=col_name)
        print(f"\n🗑  Deleted stale collection: {col_name}")
    except Exception:
        print(f"\n⚠️  Collection {col_name} did not exist — creating fresh.")

    # 3. Create fresh collection
    collection = client.create_collection(
        name=col_name,
        metadata={"hnsw:space": "cosine", "company": COMPANY},
    )
    print(f"✅  Created fresh collection: {col_name}")

    # 4. Load embedding model
    print("\n🔄  Loading embedding model (all-mpnet-base-v2)...")
    model = SentenceTransformer("all-mpnet-base-v2")
    print("    ✓ Model loaded")

    # 5. Discover files
    print("\n📂  Discovering Benchmark files...")
    all_files = discover_benchmark_files()
    print(f"\n    Total files: {len(all_files)}")

    if not all_files:
        print("\n❌  No files found. Check data/raw/Benchmark/ directory structure.")
        return

    # 6. Process and index
    total_chunks = 0
    total_files = 0

    for filepath, filing_type in all_files:
        print(f"\n  📄 {filepath.name[:60]:<60} ", end="", flush=True)

        chunks = chunk_document_with_page_parents(filepath, COMPANY)
        if not chunks:
            print("→ empty/no chunks")
            continue

        # Detect fiscal year/quarter
        sample_text = " ".join(c.content[:500] for c in chunks[:5])
        if not filing_type or filing_type == "Other":
            filing_type = detect_filing_type(filepath, sample_text)
        fy, q = get_fiscal_quarter(filepath, COMPANY, sample_text)

        child_count = sum(1 for c in chunks if c.chunk_type == "child")
        parent_count = sum(1 for c in chunks if c.chunk_type == "parent")
        table_count = sum(1 for c in chunks if c.chunk_type == "table")
        print(f"→ {len(chunks)} chunks [{fy} {q}] (C:{child_count} P:{parent_count} T:{table_count})",
              end="", flush=True)

        # Build batch
        ids, texts, metadatas = [], [], []
        for chunk in chunks:
            chunk_meta = chunk.metadata or {}
            meta = {
                "company": COMPANY,
                "source_file": filepath.name,
                "filing_type": filing_type,
                "fiscal_year": fy,
                "quarter": q,
                "chunk_type": chunk.chunk_type,
                "parent_id": chunk.parent_id,
                "parent_type": chunk.parent_type,
                "section_header": chunk_meta.get("section_header", ""),
                "section_level": chunk_meta.get("section_level", 0),
                "page_num": chunk_meta.get("page_num", 0),
                "is_parent": chunk.chunk_type == "parent",
            }
            if chunk.chunk_type == "table":
                meta["table_type"] = chunk_meta.get("table_type", "unknown")
                meta["table_context"] = chunk_meta.get("table_context", "")
            if chunk.chunk_type == "child":
                meta["child_index"] = chunk_meta.get("child_index", 0)
            ids.append(chunk.chunk_id)
            texts.append(chunk.content)
            metadatas.append(meta)

        # Embed + upsert in batches of 64
        for start in range(0, len(texts), 64):
            b_ids = ids[start:start + 64]
            b_txt = texts[start:start + 64]
            b_meta = metadatas[start:start + 64]
            embeddings = model.encode(b_txt, show_progress_bar=False)
            collection.upsert(
                ids=b_ids,
                embeddings=embeddings.tolist(),
                documents=b_txt,
                metadatas=b_meta,
            )

        total_chunks += len(chunks)
        total_files += 1
        print(" ✓")

    # 7. Summary
    print(f"\n{'=' * 65}")
    print(f"  ✅  Benchmark re-indexing complete!")
    print(f"      Files processed : {total_files}")
    print(f"      Chunks indexed  : {total_chunks}")
    print(f"      Collection size : {collection.count()}")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    main()
