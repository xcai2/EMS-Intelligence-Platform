"""
Database connections for ChromaDB.
Supports both single-collection and per-company collection modes.

Per-Company Collections (RAG-Challenge-2 style):
- Each company gets its own ChromaDB collection
- Queries are routed to specific company collections
- 100x search space reduction when filtering by company
"""
import chromadb
from sentence_transformers import SentenceTransformer
from .config import CHROMADB_PATH, EMBEDDING_MODEL, TRACKED_COMPANY_NAMES

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------
# Known companies (used for collection naming)
KNOWN_COMPANIES = list(TRACKED_COMPANY_NAMES)

# Collection naming
MAIN_COLLECTION_NAME = "capex_docs"
COMPANY_COLLECTION_PREFIX = "company_"

# ---------------------------------------------------------------------------
# CHROMADB CLIENT
# ---------------------------------------------------------------------------
_chroma_client = None
_collection = None
_company_collections = {}
_embedding_model = None


def get_chroma_client():
    """Get or create ChromaDB client."""
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=CHROMADB_PATH)
    return _chroma_client


def get_collection():
    """Get the main document collection (legacy mode)."""
    global _collection
    if _collection is None:
        client = get_chroma_client()
        _collection = client.get_or_create_collection(
            name=MAIN_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )
    return _collection


# ---------------------------------------------------------------------------
# PER-COMPANY COLLECTIONS (RAG-Challenge-2 Style)
# ---------------------------------------------------------------------------

def _normalize_company_name(company: str) -> str:
    """Normalize company name for collection naming."""
    return company.lower().replace(" ", "_").replace("-", "_")


def get_company_collection_name(company: str) -> str:
    """Get the collection name for a specific company."""
    return f"{COMPANY_COLLECTION_PREFIX}{_normalize_company_name(company)}"


def get_company_collection(company: str):
    """
    Get or create a collection for a specific company.
    
    This enables company-specific indexing which dramatically reduces
    search space when filtering by company.
    """
    global _company_collections
    
    normalized = _normalize_company_name(company)
    
    if normalized not in _company_collections:
        client = get_chroma_client()
        collection_name = get_company_collection_name(company)
        _company_collections[normalized] = client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine", "company": company}
        )
    
    return _company_collections[normalized]


def list_company_collections() -> list[str]:
    """List all company collections that exist in the database."""
    client = get_chroma_client()
    collections = client.list_collections()
    
    company_collections = []
    for col in collections:
        if col.name.startswith(COMPANY_COLLECTION_PREFIX):
            company_name = col.name[len(COMPANY_COLLECTION_PREFIX):]
            company_collections.append(company_name)
    
    return company_collections


def get_all_company_collections() -> dict:
    """
    Get all company collections as a dict mapping company name to collection.
    """
    collections = {}
    for company in KNOWN_COMPANIES:
        try:
            col = get_company_collection(company)
            if col.count() > 0:
                collections[company] = col
        except Exception:
            pass
    return collections


def has_company_collections() -> bool:
    """Check if per-company collections exist AND contain data."""
    client = get_chroma_client()
    for col_meta in list_company_collections():
        try:
            col = client.get_collection(col_meta if isinstance(col_meta, str) else col_meta.name)
            if col.count() > 0:
                return True
        except Exception:
            continue
    return False


def delete_company_collection(company: str):
    """Delete a company's collection."""
    global _company_collections
    
    client = get_chroma_client()
    collection_name = get_company_collection_name(company)
    
    try:
        client.delete_collection(name=collection_name)
        normalized = _normalize_company_name(company)
        if normalized in _company_collections:
            del _company_collections[normalized]
        return True
    except Exception:
        return False


def delete_all_company_collections():
    """Delete all company collections for fresh rebuild."""
    for company in KNOWN_COMPANIES:
        delete_company_collection(company)


def get_embedding_model():
    """Get or load the embedding model."""
    global _embedding_model
    if _embedding_model is None:
        print("Loading embedding model...")
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        print(f"✓ Loaded {EMBEDDING_MODEL}")
    return _embedding_model


def embed_text(text: str) -> list[float]:
    """Embed a single text string."""
    model = get_embedding_model()
    return model.encode(text).tolist()


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed multiple text strings."""
    model = get_embedding_model()
    return model.encode(texts).tolist()


# ---------------------------------------------------------------------------
# COLLECTION STATS
# ---------------------------------------------------------------------------

def get_collection_stats() -> dict:
    """Get statistics about the ChromaDB collection (legacy mode)."""
    collection = get_collection()
    count = collection.count()
    
    if count == 0:
        return {
            "total_documents": 0,
            "companies": {},
            "filing_types": {},
            "mode": "legacy",
        }
    
    # Get all metadata to compute stats
    results = collection.get(include=["metadatas"], limit=count)
    
    companies = {}
    filing_types = {}
    
    for meta in results["metadatas"]:
        company = meta.get("company", "Unknown")
        ftype = meta.get("filing_type", "Unknown")
        
        companies[company] = companies.get(company, 0) + 1
        filing_types[ftype] = filing_types.get(ftype, 0) + 1
    
    return {
        "total_documents": count,
        "companies": companies,
        "filing_types": filing_types,
        "mode": "legacy",
    }


def get_all_collections_stats() -> dict:
    """
    Get statistics about all collections (both legacy and per-company).
    """
    stats = {
        "mode": "per_company" if has_company_collections() else "legacy",
        "total_documents": 0,
        "companies": {},
        "collections": {},
    }
    
    # Check per-company collections
    for company in KNOWN_COMPANIES:
        try:
            col = get_company_collection(company)
            count = col.count()
            if count > 0:
                stats["companies"][company] = count
                stats["collections"][get_company_collection_name(company)] = count
                stats["total_documents"] += count
        except Exception:
            pass
    
    # Also check legacy collection
    try:
        legacy_col = get_collection()
        legacy_count = legacy_col.count()
        if legacy_count > 0:
            stats["collections"][MAIN_COLLECTION_NAME] = legacy_count
            if not stats["companies"]:
                # No per-company collections, use legacy stats
                stats["mode"] = "legacy"
                stats["total_documents"] = legacy_count
                legacy_stats = get_collection_stats()
                stats["companies"] = legacy_stats.get("companies", {})
    except Exception:
        pass
    
    return stats
