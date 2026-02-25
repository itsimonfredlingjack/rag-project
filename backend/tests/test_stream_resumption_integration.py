"""
Integration tests for StreamResumptionService wired into the streaming route.

Tests the full integration:
- X-Stream-Session header presence based on feature flag
- Event id: prefixes when resumption is enabled
- Resume endpoint replays missed events
- Resume endpoint returns 404 when feature disabled
- Resume with expired session returns error
"""

import json

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.constitutional_routes import router
from app.services.orchestrator_service import get_orchestrator_service
from app.services.stream_resumption_service import StreamResumptionService


# ── Fixtures ─────────────────────────────────────────────────────


def _make_app() -> FastAPI:
    """Create a minimal FastAPI app with our router mounted."""
    app = FastAPI()
    app.include_router(router)
    return app


def _mock_orchestrator(events: list[str] | None = None):
    """Return a mock OrchestratorService that yields SSE events."""
    orch = AsyncMock()
    event_list = events or [
        'data: {"type": "metadata", "mode": "assist", "sources": []}\n\n',
        'data: {"type": "token", "content": "Hej"}\n\n',
        'data: {"type": "token", "content": " världen"}\n\n',
        'data: {"type": "done"}\n\n',
    ]

    async def _stream(**kwargs):
        for e in event_list:
            yield e

    orch.stream_query = _stream
    return orch


def _mock_config(stream_resumption_enabled: bool = False):
    """Return a mock ConfigService with stream_resumption feature flag."""
    cfg = MagicMock()
    cfg.settings.stream_resumption_enabled = stream_resumption_enabled
    cfg.settings.stream_resumption_session_ttl = 300.0
    cfg.settings.stream_resumption_max_sessions = 100
    return cfg


# ── Tests ────────────────────────────────────────────────────────


class TestStreamSessionHeader:
    """Test X-Stream-Session header presence/absence."""

    def test_no_header_when_disabled(self):
        """When stream_resumption_enabled=false, no X-Stream-Session header."""
        app = _make_app()
        orch = _mock_orchestrator()
        cfg = _mock_config(stream_resumption_enabled=False)

        app.dependency_overrides[get_orchestrator_service] = lambda: orch
        with patch("app.api.constitutional_routes.get_config_service", return_value=cfg):
            client = TestClient(app)
            resp = client.post(
                "/api/constitutional/agent/query/stream",
                json={"question": "Vad säger RF?", "mode": "assist"},
            )
            assert resp.status_code == 200
            assert "X-Stream-Session" not in resp.headers
        app.dependency_overrides.clear()

    def test_header_present_when_enabled(self):
        """When stream_resumption_enabled=true, X-Stream-Session header is set."""
        app = _make_app()
        orch = _mock_orchestrator()
        cfg = _mock_config(stream_resumption_enabled=True)
        svc = StreamResumptionService(session_ttl=300.0, max_sessions=100)

        app.dependency_overrides[get_orchestrator_service] = lambda: orch
        with (
            patch("app.api.constitutional_routes.get_config_service", return_value=cfg),
            patch(
                "app.api.constitutional_routes.get_stream_resumption_service",
                return_value=svc,
            ),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/constitutional/agent/query/stream",
                json={"question": "Vad säger RF?", "mode": "assist"},
            )
            assert resp.status_code == 200
            assert "X-Stream-Session" in resp.headers
            session_id = resp.headers["X-Stream-Session"]
            assert len(session_id) == 12  # UUID4 hex[:12]
        app.dependency_overrides.clear()


class TestEventIdPrefixes:
    """Test that events get id: prefixes when resumption is enabled."""

    def test_events_have_id_prefix_when_enabled(self):
        """When enabled, SSE events should have 'id: N' prefixes."""
        app = _make_app()
        orch = _mock_orchestrator()
        cfg = _mock_config(stream_resumption_enabled=True)
        svc = StreamResumptionService(session_ttl=300.0, max_sessions=100)

        app.dependency_overrides[get_orchestrator_service] = lambda: orch
        with (
            patch("app.api.constitutional_routes.get_config_service", return_value=cfg),
            patch(
                "app.api.constitutional_routes.get_stream_resumption_service",
                return_value=svc,
            ),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/constitutional/agent/query/stream",
                json={"question": "Vad säger RF?", "mode": "assist"},
            )
            body = resp.text
            # Should contain "id: 1\n" for the first event
            assert "id: 1\n" in body
            # Multiple id: prefixes for each data event
            assert body.count("id: ") >= 3  # metadata + 2 tokens + done = 4
        app.dependency_overrides.clear()

    def test_no_id_prefix_when_disabled(self):
        """When disabled, SSE events should NOT have 'id: N' prefixes."""
        app = _make_app()
        orch = _mock_orchestrator()
        cfg = _mock_config(stream_resumption_enabled=False)

        app.dependency_overrides[get_orchestrator_service] = lambda: orch
        with patch("app.api.constitutional_routes.get_config_service", return_value=cfg):
            client = TestClient(app)
            resp = client.post(
                "/api/constitutional/agent/query/stream",
                json={"question": "Vad säger RF?", "mode": "assist"},
            )
            body = resp.text
            assert "id: " not in body
        app.dependency_overrides.clear()


class TestResumeEndpoint:
    """Test the POST /agent/query/stream/resume endpoint."""

    def test_resume_returns_404_when_disabled(self):
        """Resume endpoint returns 404 error when feature is disabled."""
        app = _make_app()
        cfg = _mock_config(stream_resumption_enabled=False)

        with patch("app.api.constitutional_routes.get_config_service", return_value=cfg):
            client = TestClient(app)
            resp = client.post(
                "/api/constitutional/agent/query/stream/resume",
                json={"session_id": "abc123", "last_event_id": 0},
            )
            assert resp.status_code == 404
            body = resp.text
            assert "not enabled" in body

    def test_resume_replays_missed_events(self):
        """Resume replays events after last_event_id."""
        app = _make_app()
        cfg = _mock_config(stream_resumption_enabled=True)
        svc = StreamResumptionService(session_ttl=300.0, max_sessions=100)

        # Pre-populate a session with buffered events
        session_id = svc.create_session()
        svc.buffer_event(session_id, '{"type": "token", "content": "A"}')
        svc.buffer_event(session_id, '{"type": "token", "content": "B"}')
        svc.buffer_event(session_id, '{"type": "token", "content": "C"}')

        with (
            patch("app.api.constitutional_routes.get_config_service", return_value=cfg),
            patch(
                "app.api.constitutional_routes.get_stream_resumption_service",
                return_value=svc,
            ),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/constitutional/agent/query/stream/resume",
                json={"session_id": session_id, "last_event_id": 1},
            )
            assert resp.status_code == 200
            body = resp.text
            # Should contain events 2 and 3 (after event_id=1)
            assert '"content": "B"' in body
            assert '"content": "C"' in body
            # Should NOT contain event 1
            assert '"content": "A"' not in body

    def test_resume_expired_session_returns_error(self):
        """Resume with expired/missing session returns error event."""
        app = _make_app()
        cfg = _mock_config(stream_resumption_enabled=True)
        svc = StreamResumptionService(session_ttl=300.0, max_sessions=100)

        with (
            patch("app.api.constitutional_routes.get_config_service", return_value=cfg),
            patch(
                "app.api.constitutional_routes.get_stream_resumption_service",
                return_value=svc,
            ),
        ):
            client = TestClient(app)
            resp = client.post(
                "/api/constitutional/agent/query/stream/resume",
                json={"session_id": "nonexistent123", "last_event_id": 0},
            )
            assert resp.status_code == 200
            body = resp.text
            parsed = json.loads(body.split("data: ")[1].split("\n\n")[0])
            assert parsed["type"] == "error"
            assert (
                "expired" in parsed["message"].lower() or "not found" in parsed["message"].lower()
            )
