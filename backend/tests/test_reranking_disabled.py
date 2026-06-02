from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from app.services.reranking_service import RerankingService


@pytest.mark.asyncio
async def test_disabled_reranker_does_not_lazy_load():
    config = Mock()
    config.reranking_model = "jinaai/jina-reranker-v2-base-multilingual"
    config.settings = SimpleNamespace(reranking_enabled=False)
    service = RerankingService(config)
    await service.initialize()

    with patch.object(service, "_load_model") as load_model:
        result = await service.rerank(
            "Vad säger offentlighetsprincipen?",
            [{"id": "doc_1", "title": "Doc", "snippet": "Text", "score": 0.7}],
        )

    load_model.assert_not_called()
    assert result.reranked_docs[0]["id"] == "doc_1"
    assert result.reranked_scores == [0.7]
    assert result.latency_ms == 0.0
