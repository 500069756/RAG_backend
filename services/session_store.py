"""
Session Store — Phase 11
In-memory session and thread management.

Responsibilities:
    - Thread CRUD (create, read, delete)
    - Message history per thread
    - Auto-title generation from first message
    - Session-scoped (ephemeral — no PII stored)
"""

import logging
import uuid
from collections import OrderedDict
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class SessionStore:
    """In-memory thread/message store. Ephemeral by design (no PII persistence)."""

    MAX_THREADS_PER_SESSION = 10
    MAX_MESSAGES_PER_THREAD = 50
    CONTEXT_WINDOW = 5       # Number of recent messages sent to LLM

    def __init__(self):
        # session_id -> {thread_id -> thread_data}
        self._sessions: dict[str, OrderedDict] = {}

    def _get_or_create_session(self, session_id: str) -> OrderedDict:
        """Get or create a session."""
        if session_id not in self._sessions:
            self._sessions[session_id] = OrderedDict()
        return self._sessions[session_id]

    def create_thread(self, session_id: str, thread_id: str | None = None) -> dict:
        """Create a new chat thread."""
        session = self._get_or_create_session(session_id)

        if len(session) >= self.MAX_THREADS_PER_SESSION:
            # Remove oldest thread
            oldest_key = next(iter(session))
            del session[oldest_key]
            logger.info(f"Evicted oldest thread {oldest_key} "
                        f"(session limit: {self.MAX_THREADS_PER_SESSION})")

        tid = thread_id or str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        session[tid] = {
            "thread_id": tid,
            "title": "New Conversation",
            "messages": [],
            "created_at": now,
            "last_message_at": now,
        }

        logger.info(f"Created thread {tid} (session={session_id[:8]})")
        return session[tid]

    def get_thread(self, session_id: str, thread_id: str) -> dict | None:
        """Get a thread by ID."""
        session = self._sessions.get(session_id, {})
        return session.get(thread_id)

    def list_threads(self, session_id: str) -> list[dict]:
        """List all threads for a session (newest first)."""
        session = self._sessions.get(session_id, {})
        threads = []
        for tid, data in reversed(session.items()):
            threads.append({
                "thread_id": data["thread_id"],
                "title": data["title"],
                "created_at": data["created_at"],
                "message_count": len(data["messages"]),
                "last_message_at": data["last_message_at"],
            })
        return threads

    def delete_thread(self, session_id: str, thread_id: str) -> bool:
        """Delete a thread."""
        session = self._sessions.get(session_id, {})
        if thread_id in session:
            del session[thread_id]
            logger.info(f"Deleted thread {thread_id}")
            return True
        return False

    def add_message(
        self,
        session_id: str,
        thread_id: str,
        role: str,
        content: str,
        source_url: str | None = None,
        is_refusal: bool = False,
    ) -> dict:
        """Add a message to a thread."""
        session = self._get_or_create_session(session_id)

        # Auto-create thread if it doesn't exist
        if thread_id not in session:
            self.create_thread(session_id, thread_id)

        thread = session[thread_id]
        now = datetime.now(timezone.utc).isoformat()

        message = {
            "role": role,
            "content": content,
            "timestamp": now,
            "source_url": source_url,
            "is_refusal": is_refusal,
        }

        thread["messages"].append(message)
        thread["last_message_at"] = now

        # Auto-title from first user message
        if role == "user" and thread["title"] == "New Conversation":
            thread["title"] = self._generate_title(content)

        # Enforce message limit
        if len(thread["messages"]) > self.MAX_MESSAGES_PER_THREAD:
            thread["messages"] = thread["messages"][-self.MAX_MESSAGES_PER_THREAD:]

        return message

    def get_conversation_history(
        self,
        session_id: str,
        thread_id: str
    ) -> list[dict]:
        """Get recent messages for LLM context window."""
        thread = self.get_thread(session_id, thread_id)
        if not thread:
            return []
        messages = thread["messages"]
        return messages[-self.CONTEXT_WINDOW:]

    def get_messages(self, session_id: str, thread_id: str) -> list[dict]:
        """Get all messages for a thread."""
        thread = self.get_thread(session_id, thread_id)
        if not thread:
            return []
        return thread["messages"]

    def _generate_title(self, first_message: str) -> str:
        """Generate a short title from the first user message."""
        # Take first 50 chars, trim at word boundary
        title = first_message[:50].strip()
        if len(first_message) > 50:
            # Trim to last complete word
            last_space = title.rfind(" ")
            if last_space > 20:
                title = title[:last_space]
            title += "..."
        return title
