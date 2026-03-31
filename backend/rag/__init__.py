"""RAG module for retrieval and generation."""
from .retriever import search_documents
from .generator import generate_response

# Backward-compatible exports for legacy imports.
# Chat pipeline/memory were moved under backend.aichat.
try:
    from backend.aichat.pipeline import process_query, process_query_sync
    from backend.aichat.memory import add_message, get_conversation_history
except Exception:
    pass
