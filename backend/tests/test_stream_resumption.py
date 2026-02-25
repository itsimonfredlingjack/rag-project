"""
Tests for Stream Resumption Service — SSE event buffering and replay.

Tests cover:
  - Session lifecycle (create, get, close, expire)
  - Event buffering with sequence numbers
  - Event replay after disconnection
  - Stream wrapping with SSE id: fields
  - Memory bounds (max sessions, max events)
  - Cleanup of expired sessions
"""

import json
import time

import pytest

from app.services.stream_resumption_service import (
    BufferedEvent,
    StreamResumptionService,
    StreamSession,
)


# ═══════════════════════════════════════════════════════════════════════════
# SESSION LIFECYCLE
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestSessionLifecycle:
    """Tests for stream session creation, lookup, and cleanup."""

    def test_create_session_returns_id(self):
        svc = StreamResumptionService()
        sid = svc.create_session()
        assert isinstance(sid, str)
        assert len(sid) == 12  # uuid4 hex prefix

    def test_get_session_returns_session(self):
        svc = StreamResumptionService()
        sid = svc.create_session()
        session = svc.get_session(sid)
        assert session is not None
        assert session.session_id == sid

    def test_get_nonexistent_session_returns_none(self):
        svc = StreamResumptionService()
        assert svc.get_session("nonexistent") is None

    def test_close_session_marks_completed(self):
        svc = StreamResumptionService()
        sid = svc.create_session()
        svc.close_session(sid)
        session = svc.get_session(sid)
        assert session is not None
        assert session.completed is True

    def test_session_expires_after_ttl(self):
        svc = StreamResumptionService(session_ttl=0.05)
        sid = svc.create_session()
        assert svc.get_session(sid) is not None
        time.sleep(0.06)
        assert svc.get_session(sid) is None

    def test_active_sessions_count(self):
        svc = StreamResumptionService()
        assert svc.active_sessions == 0
        svc.create_session()
        assert svc.active_sessions == 1
        svc.create_session()
        assert svc.active_sessions == 2

    def test_stats_structure(self):
        svc = StreamResumptionService()
        svc.create_session()
        stats = svc.stats()
        assert "active_sessions" in stats
        assert "max_sessions" in stats
        assert "session_ttl_seconds" in stats
        assert "total_buffered_events" in stats
        assert stats["active_sessions"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# EVENT BUFFERING
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestEventBuffering:
    """Tests for event buffering with sequence numbers."""

    def test_buffer_event_returns_sequential_ids(self):
        svc = StreamResumptionService()
        sid = svc.create_session()
        id1 = svc.buffer_event(sid, '{"type":"token","content":"a"}')
        id2 = svc.buffer_event(sid, '{"type":"token","content":"b"}')
        id3 = svc.buffer_event(sid, '{"type":"token","content":"c"}')
        assert id1 == 1
        assert id2 == 2
        assert id3 == 3

    def test_buffer_event_stores_data(self):
        svc = StreamResumptionService()
        sid = svc.create_session()
        svc.buffer_event(sid, '{"type":"token","content":"hello"}')
        session = svc.get_session(sid)
        assert session.event_count == 1
        assert session.events[0].data == '{"type":"token","content":"hello"}'

    def test_buffer_nonexistent_session_returns_none(self):
        svc = StreamResumptionService()
        result = svc.buffer_event("nonexistent", "data")
        assert result is None

    def test_buffer_expired_session_returns_none(self):
        svc = StreamResumptionService(session_ttl=0.05)
        sid = svc.create_session()
        time.sleep(0.06)
        result = svc.buffer_event(sid, "data")
        assert result is None

    def test_buffer_respects_max_events(self):
        svc = StreamResumptionService()
        svc.MAX_EVENTS_PER_SESSION = 5
        sid = svc.create_session()
        for i in range(5):
            assert svc.buffer_event(sid, f"event_{i}") is not None
        # 6th event should fail
        assert svc.buffer_event(sid, "overflow") is None

    def test_total_buffered_events_in_stats(self):
        svc = StreamResumptionService()
        sid1 = svc.create_session()
        sid2 = svc.create_session()
        svc.buffer_event(sid1, "a")
        svc.buffer_event(sid1, "b")
        svc.buffer_event(sid2, "c")
        assert svc.stats()["total_buffered_events"] == 3


# ═══════════════════════════════════════════════════════════════════════════
# STREAM SESSION DATA CLASS
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestStreamSession:
    """Tests for StreamSession dataclass methods."""

    def test_add_event_increments_counter(self):
        session = StreamSession(session_id="test")
        assert session.last_event_id == 0
        session.add_event("first")
        assert session.last_event_id == 1
        session.add_event("second")
        assert session.last_event_id == 2

    def test_get_events_after_filters_correctly(self):
        session = StreamSession(session_id="test")
        session.add_event("a")
        session.add_event("b")
        session.add_event("c")
        session.add_event("d")

        missed = session.get_events_after(2)
        assert len(missed) == 2
        assert missed[0].data == "c"
        assert missed[1].data == "d"

    def test_get_events_after_zero_returns_all(self):
        session = StreamSession(session_id="test")
        session.add_event("a")
        session.add_event("b")
        missed = session.get_events_after(0)
        assert len(missed) == 2

    def test_get_events_after_last_returns_empty(self):
        session = StreamSession(session_id="test")
        session.add_event("a")
        session.add_event("b")
        missed = session.get_events_after(2)
        assert len(missed) == 0

    def test_event_count_matches(self):
        session = StreamSession(session_id="test")
        assert session.event_count == 0
        session.add_event("x")
        session.add_event("y")
        assert session.event_count == 2

    def test_mark_completed(self):
        session = StreamSession(session_id="test")
        assert session.completed is False
        session.mark_completed()
        assert session.completed is True


# ═══════════════════════════════════════════════════════════════════════════
# BUFFERED EVENT DATA CLASS
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestBufferedEvent:
    """Tests for BufferedEvent dataclass."""

    def test_creation(self):
        event = BufferedEvent(event_id=1, data="test")
        assert event.event_id == 1
        assert event.data == "test"
        assert event.timestamp > 0


# ═══════════════════════════════════════════════════════════════════════════
# STREAM WRAPPING — SSE id: FIELDS
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestStreamWrapping:
    """Tests for wrap_with_resumption adding SSE id: fields."""

    @pytest.mark.asyncio
    async def test_wrap_adds_event_ids(self):
        svc = StreamResumptionService()
        sid = svc.create_session()

        async def mock_stream():
            yield 'data: {"type":"metadata","mode":"evidence"}\n\n'
            yield 'data: {"type":"token","content":"hello"}\n\n'
            yield 'data: {"type":"done"}\n\n'

        events = []
        async for event in svc.wrap_with_resumption(mock_stream(), sid):
            events.append(event)

        assert len(events) == 3
        # Each event should have an id: prefix
        assert events[0].startswith("id: 1\ndata: ")
        assert events[1].startswith("id: 2\ndata: ")
        assert events[2].startswith("id: 3\ndata: ")

    @pytest.mark.asyncio
    async def test_wrap_skips_pings(self):
        svc = StreamResumptionService()
        sid = svc.create_session()

        async def mock_stream():
            yield 'data: {"type":"token","content":"a"}\n\n'
            yield ":ping\n\n"
            yield 'data: {"type":"token","content":"b"}\n\n'

        events = []
        async for event in svc.wrap_with_resumption(mock_stream(), sid):
            events.append(event)

        assert len(events) == 3
        # Ping should pass through unchanged
        assert events[1] == ":ping\n\n"
        # Data events should have ids
        assert events[0].startswith("id: 1\n")
        assert events[2].startswith("id: 2\n")

    @pytest.mark.asyncio
    async def test_wrap_buffers_events(self):
        svc = StreamResumptionService()
        sid = svc.create_session()

        async def mock_stream():
            yield 'data: {"type":"token","content":"hello"}\n\n'
            yield 'data: {"type":"done"}\n\n'

        async for _ in svc.wrap_with_resumption(mock_stream(), sid):
            pass

        # Session should have buffered events
        session = svc.get_session(sid)
        assert session is not None
        assert session.event_count == 2
        assert session.completed is True

    @pytest.mark.asyncio
    async def test_wrap_marks_completed_on_finish(self):
        svc = StreamResumptionService()
        sid = svc.create_session()

        async def mock_stream():
            yield 'data: {"type":"done"}\n\n'

        async for _ in svc.wrap_with_resumption(mock_stream(), sid):
            pass

        session = svc.get_session(sid)
        assert session.completed is True


# ═══════════════════════════════════════════════════════════════════════════
# EVENT REPLAY
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestEventReplay:
    """Tests for replaying missed events on reconnection."""

    @pytest.mark.asyncio
    async def test_replay_missed_events(self):
        svc = StreamResumptionService()
        sid = svc.create_session()

        # Buffer 5 events
        for i in range(5):
            svc.buffer_event(sid, json.dumps({"type": "token", "content": f"t{i}"}))

        # Client received up to event 2, replay from 3
        events = []
        async for event in svc.replay_missed_events(sid, last_event_id=2):
            events.append(event)

        assert len(events) == 3  # Events 3, 4, 5
        assert "id: 3\n" in events[0]
        assert "id: 4\n" in events[1]
        assert "id: 5\n" in events[2]

    @pytest.mark.asyncio
    async def test_replay_expired_session(self):
        svc = StreamResumptionService(session_ttl=0.05)
        sid = svc.create_session()
        svc.buffer_event(sid, '{"type":"token"}')
        time.sleep(0.06)

        events = []
        async for event in svc.replay_missed_events(sid, last_event_id=0):
            events.append(event)

        assert len(events) == 1
        data = json.loads(events[0].split("data: ")[1].strip())
        assert data["type"] == "error"
        assert "expired" in data["message"].lower() or "not found" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_replay_nonexistent_session(self):
        svc = StreamResumptionService()
        events = []
        async for event in svc.replay_missed_events("nonexistent", last_event_id=0):
            events.append(event)

        assert len(events) == 1
        data = json.loads(events[0].split("data: ")[1].strip())
        assert data["type"] == "error"

    @pytest.mark.asyncio
    async def test_replay_completed_session_includes_signal(self):
        svc = StreamResumptionService()
        sid = svc.create_session()
        svc.buffer_event(sid, '{"type":"token","content":"a"}')
        svc.buffer_event(sid, '{"type":"done"}')
        svc.close_session(sid)

        events = []
        async for event in svc.replay_missed_events(sid, last_event_id=0):
            events.append(event)

        # Should have 2 buffered events + 1 replay_complete signal
        assert len(events) == 3
        last_data = json.loads(events[-1].split("data: ")[1].strip())
        assert last_data["type"] == "replay_complete"
        assert last_data["replayed"] == 2

    @pytest.mark.asyncio
    async def test_replay_from_last_event_returns_empty_if_caught_up(self):
        svc = StreamResumptionService()
        sid = svc.create_session()
        svc.buffer_event(sid, '{"type":"token"}')
        svc.buffer_event(sid, '{"type":"done"}')

        events = []
        async for event in svc.replay_missed_events(sid, last_event_id=2):
            events.append(event)

        # No missed events (client was caught up)
        assert len(events) == 0


# ═══════════════════════════════════════════════════════════════════════════
# MEMORY BOUNDS
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestMemoryBounds:
    """Tests for memory-bounded session management."""

    def test_evicts_oldest_when_full(self):
        svc = StreamResumptionService(max_sessions=3)
        s1 = svc.create_session()
        s2 = svc.create_session()
        svc.create_session()  # s3 — will be evicted
        assert svc.active_sessions == 3

        # Creating a 4th should evict s1
        s4 = svc.create_session()
        assert svc.active_sessions == 3
        assert svc.get_session(s1) is None  # Evicted
        assert svc.get_session(s2) is not None
        assert svc.get_session(s4) is not None

    def test_cleanup_expired_removes_old_sessions(self):
        svc = StreamResumptionService(session_ttl=0.05)
        svc.create_session()
        svc.create_session()
        assert svc.active_sessions == 2

        time.sleep(0.06)
        removed = svc.cleanup_expired()
        assert removed == 2
        assert svc.active_sessions == 0

    def test_cleanup_keeps_fresh_sessions(self):
        svc = StreamResumptionService(session_ttl=10.0)
        svc.create_session()
        svc.create_session()
        removed = svc.cleanup_expired()
        assert removed == 0
        assert svc.active_sessions == 2

    def test_max_events_per_session_safety(self):
        svc = StreamResumptionService()
        svc.MAX_EVENTS_PER_SESSION = 10
        sid = svc.create_session()

        for i in range(10):
            assert svc.buffer_event(sid, f"event_{i}") is not None

        # 11th should return None
        assert svc.buffer_event(sid, "overflow") is None

        # Session should still work — just can't buffer more
        session = svc.get_session(sid)
        assert session.event_count == 10


# ═══════════════════════════════════════════════════════════════════════════
# FULL INTEGRATION SCENARIO
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestFullReconnectionScenario:
    """End-to-end reconnection scenario tests."""

    @pytest.mark.asyncio
    async def test_disconnect_and_reconnect(self):
        """Simulate: client connects, receives 3 tokens, disconnects, reconnects."""
        svc = StreamResumptionService()
        sid = svc.create_session()

        # Original stream produces 5 tokens + done
        async def original_stream():
            for i in range(5):
                yield f"data: {json.dumps({'type': 'token', 'content': f'word{i}'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        # Client consumes first 3 events then "disconnects"
        received = []
        gen = svc.wrap_with_resumption(original_stream(), sid)
        async for event in gen:
            received.append(event)
            if len(received) == 3:
                break
        await gen.aclose()

        # Session should have 3 buffered events (early close buffers what was consumed)
        session = svc.get_session(sid)
        assert session is not None
        assert session.event_count == 3

        # Now "reconnect" — buffer the remaining events manually
        # (In real usage, the stream would continue; here we simulate replay)
        for i in range(3, 5):
            svc.buffer_event(sid, json.dumps({"type": "token", "content": f"word{i}"}))
        svc.buffer_event(sid, json.dumps({"type": "done"}))
        svc.close_session(sid)

        # Replay from last received event (3)
        replayed = []
        async for event in svc.replay_missed_events(sid, last_event_id=3):
            replayed.append(event)

        # Should get events 4, 5, 6 + replay_complete
        assert len(replayed) == 4
        assert "id: 4\n" in replayed[0]
        assert "id: 5\n" in replayed[1]
        assert "id: 6\n" in replayed[2]

    @pytest.mark.asyncio
    async def test_multiple_concurrent_sessions(self):
        """Multiple sessions should be independent."""
        svc = StreamResumptionService()
        s1 = svc.create_session()
        s2 = svc.create_session()

        svc.buffer_event(s1, '{"type":"token","content":"session1"}')
        svc.buffer_event(s2, '{"type":"token","content":"session2_a"}')
        svc.buffer_event(s2, '{"type":"token","content":"session2_b"}')

        session1 = svc.get_session(s1)
        session2 = svc.get_session(s2)
        assert session1.event_count == 1
        assert session2.event_count == 2

        # Replay s2 from 0
        events = []
        async for event in svc.replay_missed_events(s2, last_event_id=0):
            events.append(event)
        assert len(events) == 2
        assert "session2_a" in events[0]
        assert "session2_b" in events[1]
