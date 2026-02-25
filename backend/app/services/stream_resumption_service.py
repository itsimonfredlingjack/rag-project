"""
Stream Resumption Service — SSE event buffering for connection recovery.

Allows clients to resume interrupted SSE streams by replaying buffered events.
Uses the standard SSE `id:` field and `Last-Event-ID` header for reconnection.

Architecture:
  - Each streaming query creates a session with a unique ID
  - Events are numbered and buffered in memory
  - On reconnection, missed events are replayed before live streaming resumes
  - Sessions expire after a configurable TTL (default: 5 minutes)
"""

import asyncio
import json
import logging
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import lru_cache
from typing import AsyncGenerator, Optional

logger = logging.getLogger("constitutional.stream_resumption")


@dataclass
class BufferedEvent:
    """A single SSE event stored in the buffer."""

    event_id: int
    data: str  # The raw SSE data payload (after "data: " prefix)
    timestamp: float = field(default_factory=time.monotonic)


@dataclass
class StreamSession:
    """
    Represents a single streaming query session.

    Buffers events for potential replay on reconnection.
    """

    session_id: str
    created_at: float = field(default_factory=time.monotonic)
    events: list = field(default_factory=list)
    _event_counter: int = 0
    completed: bool = False

    def add_event(self, data: str) -> int:
        """
        Buffer an event and return its sequence ID.

        Args:
            data: The raw SSE data string (without "data: " prefix)

        Returns:
            The assigned event ID
        """
        self._event_counter += 1
        event = BufferedEvent(
            event_id=self._event_counter,
            data=data,
        )
        self.events.append(event)
        return self._event_counter

    def get_events_after(self, last_event_id: int) -> list[BufferedEvent]:
        """
        Get all events after the given ID.

        Args:
            last_event_id: The last event ID the client received

        Returns:
            List of buffered events with ID > last_event_id
        """
        return [e for e in self.events if e.event_id > last_event_id]

    @property
    def event_count(self) -> int:
        return len(self.events)

    @property
    def last_event_id(self) -> int:
        return self._event_counter

    def mark_completed(self) -> None:
        self.completed = True


class StreamResumptionService:
    """
    Manages SSE stream sessions for connection resumption.

    Features:
    - Session creation with unique IDs
    - Event buffering with sequence numbers
    - Replay of missed events on reconnection
    - Automatic session expiry (TTL-based cleanup)
    - Memory-bounded (max sessions limit)

    Thread Safety:
        - Session dict access is single-threaded (asyncio event loop)
        - Cleanup runs as a background task
    """

    # Defaults
    DEFAULT_SESSION_TTL = 300.0  # 5 minutes
    MAX_SESSIONS = 100  # Max concurrent sessions in buffer
    MAX_EVENTS_PER_SESSION = 5000  # Safety limit per session

    def __init__(
        self,
        session_ttl: float = DEFAULT_SESSION_TTL,
        max_sessions: int = MAX_SESSIONS,
    ):
        self._sessions: OrderedDict[str, StreamSession] = OrderedDict()
        self._session_ttl = session_ttl
        self._max_sessions = max_sessions
        self._cleanup_task: Optional[asyncio.Task] = None
        logger.info(f"StreamResumptionService initialized (ttl={session_ttl}s, max={max_sessions})")

    # ─── Session Lifecycle ────────────────────────────────────────

    def create_session(self) -> str:
        """
        Create a new stream session.

        Returns:
            Unique session ID (UUID4 prefix)
        """
        self._evict_if_full()
        session_id = uuid.uuid4().hex[:12]
        self._sessions[session_id] = StreamSession(session_id=session_id)
        logger.debug(f"Stream session created: {session_id}")
        return session_id

    def get_session(self, session_id: str) -> Optional[StreamSession]:
        """Get a session by ID, or None if expired/missing."""
        session = self._sessions.get(session_id)
        if session is None:
            return None
        # Check TTL
        if time.monotonic() - session.created_at > self._session_ttl:
            del self._sessions[session_id]
            logger.debug(f"Stream session expired: {session_id}")
            return None
        return session

    def close_session(self, session_id: str) -> None:
        """Mark session as completed (will be cleaned up by TTL)."""
        session = self._sessions.get(session_id)
        if session:
            session.mark_completed()

    # ─── Event Buffering ──────────────────────────────────────────

    def buffer_event(self, session_id: str, data: str) -> Optional[int]:
        """
        Buffer an SSE event for a session.

        Args:
            session_id: The session to buffer for
            data: The raw SSE data payload

        Returns:
            The event ID, or None if session not found / at capacity
        """
        session = self.get_session(session_id)
        if session is None:
            return None
        if session.event_count >= self.MAX_EVENTS_PER_SESSION:
            logger.warning(f"Session {session_id} hit event limit ({self.MAX_EVENTS_PER_SESSION})")
            return None
        return session.add_event(data)

    # ─── Stream Wrapping ─────────────────────────────────────────

    async def wrap_with_resumption(
        self,
        event_generator: AsyncGenerator[str, None],
        session_id: str,
    ) -> AsyncGenerator[str, None]:
        """
        Wrap an SSE generator to add event IDs and buffer events.

        Each yielded event gets an `id:` field for SSE resumption.
        Events are buffered so they can be replayed on reconnection.

        Args:
            event_generator: The original SSE event generator
            session_id: The session ID for this stream

        Yields:
            SSE-formatted events with id: fields
        """
        try:
            async for raw_event in event_generator:
                # Skip ping/comment lines — don't buffer those
                if raw_event.startswith(":"):
                    yield raw_event
                    continue

                # Extract the data payload from "data: {...}\n\n"
                if raw_event.startswith("data: "):
                    data_payload = raw_event[6:].rstrip("\n")
                    event_id = self.buffer_event(session_id, data_payload)
                    if event_id is not None:
                        yield f"id: {event_id}\n{raw_event}"
                    else:
                        yield raw_event
                else:
                    yield raw_event
        finally:
            self.close_session(session_id)

    async def replay_missed_events(
        self,
        session_id: str,
        last_event_id: int,
    ) -> AsyncGenerator[str, None]:
        """
        Replay events missed after a disconnection.

        Args:
            session_id: The session to replay from
            last_event_id: The last event ID the client received

        Yields:
            SSE-formatted events that the client missed
        """
        session = self.get_session(session_id)
        if session is None:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Session expired or not found'})}\n\n"
            return

        missed = session.get_events_after(last_event_id)
        logger.info(
            f"Replaying {len(missed)} events for session {session_id} "
            f"(after event_id={last_event_id})"
        )

        for event in missed:
            yield f"id: {event.event_id}\ndata: {event.data}\n\n"

        # If session is completed, send done signal
        if session.completed:
            yield f"data: {json.dumps({'type': 'replay_complete', 'replayed': len(missed)})}\n\n"

    # ─── Cleanup ──────────────────────────────────────────────────

    def _evict_if_full(self) -> None:
        """Evict oldest sessions if at capacity."""
        while len(self._sessions) >= self._max_sessions:
            oldest_id, _ = self._sessions.popitem(last=False)
            logger.debug(f"Evicted oldest session: {oldest_id}")

    def cleanup_expired(self) -> int:
        """
        Remove expired sessions. Returns number removed.

        Call periodically or before creating new sessions.
        """
        now = time.monotonic()
        expired = [
            sid
            for sid, session in self._sessions.items()
            if now - session.created_at > self._session_ttl
        ]
        for sid in expired:
            del self._sessions[sid]
        if expired:
            logger.debug(f"Cleaned up {len(expired)} expired stream sessions")
        return len(expired)

    @property
    def active_sessions(self) -> int:
        """Number of active (non-expired) sessions."""
        return len(self._sessions)

    def stats(self) -> dict:
        """Return service statistics."""
        return {
            "active_sessions": self.active_sessions,
            "max_sessions": self._max_sessions,
            "session_ttl_seconds": self._session_ttl,
            "total_buffered_events": sum(s.event_count for s in self._sessions.values()),
        }


@lru_cache()
def get_stream_resumption_service() -> StreamResumptionService:
    """Get singleton StreamResumptionService."""
    return StreamResumptionService()
