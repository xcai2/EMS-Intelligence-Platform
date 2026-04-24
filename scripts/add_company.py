#!/usr/bin/env python3
"""
add_company.py — Incrementally embed a SINGLE company into ChromaDB.

Unlike build_chromadb.py (which deletes and rebuilds ALL company collections),
this script only rebuilds the target company's collection. The other companies'
existing collections are untouched.

Usage:
    python scripts/add_company.py                    # default: Plexus
    python scripts/add_company.py --company Plexus
    python scripts/add_company.py --company Jabil    # re-embed just Jabil

Prerequisites (same as build_chromadb.py):
    - venv activated
    - Raw files placed under data/raw/<Company>/<subfolder>/
    - The company is present in SOURCES / COMPANY_DISPLAY in build_chromadb.py
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import chromadb
from sentence_transformers import SentenceTransformer

from scripts.build_chromadb import (
    SOURCES,
    COMPANY_DISPLAY,
    RAW_DATA_DIR,
    DB_PATH,
    chunk_document_with_page_parents,
    detect_filing_type,
    get_fiscal_quarter,
    _get_company_collection_name,
)


def add_company(company_folder: str) -> None:
    if company_folder not in SOURCES:
        sys.exit(
            f"❌ '{company_folder}' not in SOURCES.\n"
            f"   Available: {list(SOURCES.keys())}"
        )

    display = COMPANY_DISPLAY[company_folder]
    col_name = _get_company_collection_name(display)

    print("=" * 70)
    print(f"  INCREMENTAL EMBED — {display}")
    print(f"  Collection: {col_name}")
    print(f"  DB path:    {DB_PATH}")
    print(f"  Other companies' collections will NOT be touched.")
    print("=" * 70)

    client = chromadb.PersistentClient(path=DB_PATH)

    try:
        client.delete_collection(name=col_name)
        print(f"\n   Deleted existing {col_name} (rebuilding this company only)")
    except Exception:
        print(f"\n   No existing {col_name} — creating fresh")

    collection = client.create_collection(
        name=col_name,
        metadata={"hnsw:space": "cosine", "company": display},
    )

    company_path = RAW_DATA_DIR / company_folder
    if not company_path.is_dir():
        sys.exit(f"❌ Raw folder not found: {company_path}")

    files_to_process = []
    for subdir_name, ftype in SOURCES[company_folder]:
        subdir_path = company_path / subdir_name
        if not subdir_path.is_dir():
            print(f"   ⚠️  Missing subfolder: {subdir_name}")
            continue
        for f in sorted(subdir_path.rglob("*")):
            if f.is_file() and f.suffix.lower() in {".pdf", ".html", ".htm"}:
                files_to_process.append((f, display, ftype))

    if not files_to_process:
        sys.exit("❌ No files found. Check the raw subfolders.")

    print(f"\n📂 Found {len(files_to_process)} files for {display}")

    print("\n🔄 Loading embedding model (all-mpnet-base-v2)...")
    model = SentenceTransformer("all-mpnet-base-v2")
    print("   ✓ Model loaded (768-dim vectors)")

    total_chunks = 0
    for filepath, comp, filing_type in files_to_process:
        print(f"  📄 {filepath.name[:60]:<60} ", end="", flush=True)
        chunks = chunk_document_with_page_parents(filepath, comp)
        if not chunks:
            print("→ empty")
            continue

        sample_text = " ".join(c.content[:500] for c in chunks[:5])
        if not filing_type or filing_type == "Other":
            filing_type = detect_filing_type(filepath, sample_text)
        fy, q = get_fiscal_quarter(filepath, comp, sample_text)

        ids, texts, metas = [], [], []
        for ch in chunks:
            ids.append(ch.chunk_id)
            texts.append(ch.content)
            cm = ch.metadata or {}
            meta = {
                "company": comp,
                "source_file": filepath.name,
                "filing_type": filing_type,
                "fiscal_year": fy,
                "quarter": q,
                "chunk_type": ch.chunk_type,
                "parent_id": ch.parent_id,
                "parent_type": ch.parent_type,
                "section_header": cm.get("section_header", ""),
                "section_level": cm.get("section_level", 0),
                "page_num": cm.get("page_num", 0),
                "is_parent": ch.chunk_type == "parent",
            }
            if ch.chunk_type == "table":
                meta["table_type"] = cm.get("table_type", "unknown")
                meta["table_context"] = cm.get("table_context", "")
            if ch.chunk_type == "child":
                meta["child_index"] = cm.get("child_index", 0)
            metas.append(meta)

        c_cnt = sum(1 for x in chunks if x.chunk_type == "child")
        p_cnt = sum(1 for x in chunks if x.chunk_type == "parent")
        t_cnt = sum(1 for x in chunks if x.chunk_type == "table")
        print(f"→ {len(chunks)} chunks (C:{c_cnt} P:{p_cnt} T:{t_cnt})", end="", flush=True)

        for start in range(0, len(texts), 64):
            emb = model.encode(texts[start:start + 64], show_progress_bar=False)
            collection.upsert(
                ids=ids[start:start + 64],
                embeddings=emb.tolist(),
                documents=texts[start:start + 64],
                metadatas=metas[start:start + 64],
            )
        total_chunks += len(chunks)
        print(" ✓")

    print(f"\n✅ Done. '{col_name}' contains {total_chunks} chunks ({len(files_to_process)} files).")
    print("   Other company collections were NOT modified.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Embed a single company into ChromaDB without touching the others."
    )
    parser.add_argument(
        "--company",
        default="Plexus",
        help="SOURCES key (default: Plexus). Examples: Plexus, Jabil, Flex, Sanmina, Benchmark, Celestica/Celestica",
    )
    args = parser.parse_args()
    add_company(args.company)
