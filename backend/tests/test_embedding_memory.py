"""
Tests for Embedding Service memory management.

Verifies that _encode() wraps inference in torch.no_grad() and calls gc.collect(),
and that unload() frees the model and calls gc.collect().
"""

from unittest.mock import MagicMock, patch

import pytest

from app.services.embedding_service import EmbeddingService


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset singleton between tests."""
    EmbeddingService._instance = None
    yield
    EmbeddingService._instance = None


@pytest.fixture
def service():
    config = MagicMock()
    config.embedding_model = "jinaai/jina-embeddings-v3"
    config.expected_embedding_dim = 1024
    return EmbeddingService(config)


class TestEncodeMemoryCleanup:
    """Tests that _encode() performs memory cleanup after inference."""

    @patch("app.services.embedding_service.gc")
    @patch("app.services.embedding_service.torch")
    def test_encode_calls_gc_collect(self, mock_torch, mock_gc, service):
        """_encode() should call gc.collect() after encoding."""
        import numpy as np

        # Setup mock model
        mock_model = MagicMock()
        fake_embeddings = np.array([[0.1, 0.2, 0.3]])
        mock_model.encode.return_value = fake_embeddings
        service._model = mock_model
        service._is_loaded = True

        service._encode(["test text"])

        mock_gc.collect.assert_called_once()

    @patch("app.services.embedding_service.gc")
    @patch("app.services.embedding_service.torch")
    def test_encode_uses_no_grad(self, mock_torch, mock_gc, service):
        """_encode() should wrap inference in torch.no_grad()."""
        import numpy as np

        mock_model = MagicMock()
        fake_embeddings = np.array([[0.1, 0.2, 0.3]])
        mock_model.encode.return_value = fake_embeddings
        service._model = mock_model
        service._is_loaded = True

        service._encode(["test text"])

        mock_torch.no_grad.assert_called_once()


class TestUnloadMemoryCleanup:
    """Tests that unload() frees model and collects garbage."""

    @patch("app.services.embedding_service.gc")
    @patch("app.services.embedding_service.torch")
    def test_unload_calls_gc_collect(self, mock_torch, mock_gc, service):
        """unload() should call gc.collect() after deleting model."""
        service._model = MagicMock()
        service._is_loaded = True

        service.unload()

        assert service._model is None
        assert service._is_loaded is False
        mock_gc.collect.assert_called_once()

    @patch("app.services.embedding_service.gc")
    @patch("app.services.embedding_service.torch")
    def test_unload_clears_cuda_cache_when_available(self, mock_torch, mock_gc, service):
        """unload() should call torch.cuda.empty_cache() if CUDA is available."""
        mock_torch.cuda.is_available.return_value = True
        service._model = MagicMock()
        service._is_loaded = True

        service.unload()

        mock_torch.cuda.empty_cache.assert_called_once()

    @patch("app.services.embedding_service.gc")
    @patch("app.services.embedding_service.torch")
    def test_unload_skips_cuda_when_unavailable(self, mock_torch, mock_gc, service):
        """unload() should skip torch.cuda.empty_cache() when CUDA is not available."""
        mock_torch.cuda.is_available.return_value = False
        service._model = MagicMock()
        service._is_loaded = True

        service.unload()

        mock_torch.cuda.empty_cache.assert_not_called()

    @patch("app.services.embedding_service.gc")
    @patch("app.services.embedding_service.torch")
    def test_unload_noop_when_no_model(self, mock_torch, mock_gc, service):
        """unload() should be a no-op when model is not loaded."""
        service._model = None
        service._is_loaded = False

        service.unload()

        mock_gc.collect.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
