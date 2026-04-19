"""
Session & Thread Manager — Phase 5.4
Manages chat threads and message history.

Responsibilities:
    - Create/manage chat threads
    - Store message history per thread
    - Thread CRUD operations
    - In-memory session storage (can be upgraded to Redis later)
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """Single message in a chat thread."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: str
    source_url: Optional[str] = None
    is_refusal: bool = False
    confidence_score: Optional[float] = None


@dataclass
class ChatThread:
    """A complete chat thread with messages."""
    thread_id: str
    title: str
    created_at: str
    messages: list[Message] = field(default_factory=list)

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def last_message_at(self) -> Optional[str]:
        return self.messages[-1].timestamp if self.messages else None


class SessionManager:
    """
    Manages chat threads and message history.
    
    Uses in-memory storage (dictionary).
    For production with multiple workers, use Redis or database.
    """

    MAX_THREADS_PER_SESSION = 50
    MAX_MESSAGES_PER_THREAD = 100

    def __init__(self):
        # thread_id -> ChatThread
        self.threads: dict[str, ChatThread] = {}
        logger.info("Session manager initialized (in-memory storage)")

    def create_thread(self, first_message: Optional[str] = None) -> ChatThread:
        """
        Create a new chat thread.

        Args:
            first_message: Optional first message to set thread title

        Returns:
            New ChatThread instance
        """
        thread_id = str(uuid.uuid4())
        
        # Generate title from first message or default
        if first_message:
            title = first_message[:50] + ("..." if len(first_message) > 50 else "")
        else:
            title = f"Thread {len(self.threads) + 1}"

        thread = ChatThread(
            thread_id=thread_id,
            title=title,
            created_at=datetime.now(timezone.utc).isoformat()
        )

        self.threads[thread_id] = thread
        logger.info(f"Created thread: {thread_id} (title: {title})")

        return thread

    def add_message(
        self,
        thread_id: str,
        role: str,
        content: str,
        source_url: Optional[str] = None,
        is_refusal: bool = False,
        confidence_score: Optional[float] = None,
    ) -> Message:
        """
        Add a message to an existing thread.

        Args:
            thread_id: Thread ID
            role: "user" or "assistant"
            content: Message content
            source_url: Source citation URL (for assistant messages)
            is_refusal: Whether this is a refusal response
            confidence_score: Confidence score (for assistant messages)

        Returns:
            Created Message instance

        Raises:
            ValueError: If thread doesn't exist
        """
        if thread_id not in self.threads:
            raise ValueError(f"Thread not found: {thread_id}")

        thread = self.threads[thread_id]

        # Enforce max messages limit
        if len(thread.messages) >= self.MAX_MESSAGES_PER_THREAD:
            # Remove oldest message
            thread.messages.pop(0)
            logger.debug(f"Thread {thread_id} exceeded max messages, removed oldest")

        message = Message(
            role=role,
            content=content,
            timestamp=datetime.now(timezone.utc).isoformat(),
            source_url=source_url,
            is_refusal=is_refusal,
            confidence_score=confidence_score
        )

        thread.messages.append(message)
        logger.debug(f"Added {role} message to thread {thread_id}")

        return message

    def get_thread(self, thread_id: str) -> Optional[ChatThread]:
        """Get a thread by ID."""
        return self.threads.get(thread_id)

    def get_threads(self) -> list[ChatThread]:
        """Get all threads, sorted by creation time (newest first)."""
        return sorted(
            self.threads.values(),
            key=lambda t: t.created_at,
            reverse=True
        )

    def get_thread_messages(self, thread_id: str) -> list[Message]:
        """Get all messages in a thread."""
        thread = self.get_thread(thread_id)
        if not thread:
            return []
        return thread.messages

    def delete_thread(self, thread_id: str) -> bool:
        """
        Delete a thread and all its messages.

        Returns:
            True if thread was deleted, False if not found
        """
        if thread_id in self.threads:
            del self.threads[thread_id]
            logger.info(f"Deleted thread: {thread_id}")
            return True
        return False

    def cleanup_old_threads(self, max_age_hours: int = 24):
        """
        Remove threads older than specified age.

        Args:
            max_age_hours: Maximum age in hours
        """
        now = datetime.now(timezone.utc)
        threads_to_delete = []

        for thread_id, thread in self.threads.items():
            created = datetime.fromisoformat(thread.created_at)
            age_hours = (now - created).total_seconds() / 3600

            if age_hours > max_age_hours:
                threads_to_delete.append(thread_id)

        for thread_id in threads_to_delete:
            del self.threads[thread_id]

        if threads_to_delete:
            logger.info(f"Cleaned up {len(threads_to_delete)} old threads")

    def get_or_create_thread(self, thread_id: Optional[str] = None) -> ChatThread:
        """
        Get existing thread or create new one.

        Args:
            thread_id: Optional thread ID (if None, creates new)

        Returns:
            ChatThread instance
        """
        if thread_id and thread_id in self.threads:
            return self.threads[thread_id]
        
        return self.create_thread()
