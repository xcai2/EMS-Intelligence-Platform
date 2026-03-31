"""
Conversation memory for multi-turn chat.
Uses in-memory storage (no external dependencies).
"""
from typing import Optional
from collections import defaultdict
from datetime import datetime, timedelta

# In-memory session storage
_sessions: dict[str, dict] = defaultdict(lambda: {
    "messages": [],
    "created_at": datetime.now(),
    "last_accessed": datetime.now(),
})

# Maximum messages to keep per session
MAX_MESSAGES = 20
# Session expiry time
SESSION_EXPIRY_HOURS = 24


def get_session(session_id: str) -> dict:
    """Get or create a session."""
    session = _sessions[session_id]
    session["last_accessed"] = datetime.now()
    return session


def add_message(session_id: str, role: str, content: str) -> None:
    """Add a message to the session history."""
    session = get_session(session_id)
    
    session["messages"].append({
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat(),
    })
    
    # Trim old messages if needed
    if len(session["messages"]) > MAX_MESSAGES:
        # Keep system context and recent messages
        session["messages"] = session["messages"][-MAX_MESSAGES:]


def get_conversation_history(session_id: str) -> list[dict]:
    """Get conversation history formatted for Claude API."""
    session = get_session(session_id)
    
    # Return messages in Claude format (role, content only)
    return [
        {"role": msg["role"], "content": msg["content"]}
        for msg in session["messages"]
    ]


def clear_session(session_id: str) -> None:
    """Clear a session's history."""
    if session_id in _sessions:
        del _sessions[session_id]


def get_session_info(session_id: str) -> dict:
    """Get session metadata."""
    session = get_session(session_id)
    return {
        "session_id": session_id,
        "message_count": len(session["messages"]),
        "created_at": session["created_at"].isoformat(),
        "last_accessed": session["last_accessed"].isoformat(),
    }


def cleanup_expired_sessions() -> int:
    """Remove expired sessions. Returns count of removed sessions."""
    now = datetime.now()
    expiry_threshold = timedelta(hours=SESSION_EXPIRY_HOURS)
    
    expired = [
        sid for sid, session in _sessions.items()
        if now - session["last_accessed"] > expiry_threshold
    ]
    
    for sid in expired:
        del _sessions[sid]
    
    return len(expired)


def get_all_sessions() -> list[dict]:
    """Get info about all active sessions (for debugging/admin)."""
    return [
        {
            "session_id": sid,
            "message_count": len(session["messages"]),
            "last_accessed": session["last_accessed"].isoformat(),
        }
        for sid, session in _sessions.items()
    ]
