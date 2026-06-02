from types import SimpleNamespace

import pytest

from app.services.query_processor_service import ResponseMode
from app.services.rag_models import RAGPipelineMetrics, RAGResult
from app.services.retrieval_service import SearchResult


def _make_result() -> RAGResult:
    metrics = RAGPipelineMetrics()
    metrics.retrieval_strategy = "adaptive"
    metrics.retrieval_ms = 321.0
    metrics.total_pipeline_ms = 987.0

    return RAGResult(
        answer="Det här är ett källgrundat svar.",
        sources=[
            SearchResult(
                id="doc-1",
                title="Regeringsformen 2 kap. 1 §",
                snippet="Var och en är gentemot det allmänna tillförsäkrad yttrandefrihet.",
                score=0.92,
                source="sfs_lagtext_jina_v3_1024",
                doc_type="sfs",
                date="2024-01-01",
                retriever="dense",
                tier="A",
            )
        ],
        reasoning_steps=["Klassificerade fråga", "Körde retrieval", "Genererade svar"],
        metrics=metrics,
        mode=ResponseMode.EVIDENCE,
        guardrail_status=SimpleNamespace(value="unchanged"),
        evidence_level="HIGH",
        citations=[],
        intent="legal_text",
        success=True,
        thought_chain="Noggrann bedömning av hämtade källor.",
    )


def test_build_query_tool_payload_shapes_model_and_widget_data():
    from app.chatgpt_app.adapters import build_query_tool_payload

    payload = build_query_tool_payload(_make_result())

    assert payload["structured_content"]["answer"] == "Det här är ett källgrundat svar."
    assert payload["structured_content"]["evidence_level"] == "HIGH"
    assert payload["structured_content"]["source_count"] == 1
    assert payload["structured_content"]["retrieval_strategy"] == "adaptive"
    assert payload["structured_content"]["intent"] == "legal_text"

    assert payload["meta"]["sources"][0]["id"] == "doc-1"
    assert payload["meta"]["sources"][0]["title"] == "Regeringsformen 2 kap. 1 §"
    assert payload["meta"]["thought_chain"] == "Noggrann bedömning av hämtade källor."
    assert payload["meta"]["reasoning_steps"] == [
        "Klassificerade fråga",
        "Körde retrieval",
        "Genererade svar",
    ]


def test_build_query_tool_payload_marks_refusal_when_sources_missing():
    from app.chatgpt_app.adapters import build_query_tool_payload

    result = _make_result()
    result.answer = "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats..."
    result.sources = []
    result.evidence_level = "NONE"

    payload = build_query_tool_payload(result)

    assert payload["structured_content"]["refusal"] is True
    assert payload["structured_content"]["source_count"] == 0
    assert payload["meta"]["sources"] == []


@pytest.mark.parametrize(
    ("view", "expected_title"),
    [
        ("query", "Svensk Ragg Query Report"),
        ("operator", "Svensk Ragg Operator Dashboard"),
    ],
)
def test_widget_html_contains_bridge_and_expected_view_titles(view: str, expected_title: str):
    from app.chatgpt_app.widget import build_widget_html

    html = build_widget_html(default_view=view)

    assert "ui/notifications/tool-result" in html
    assert "tools/call" in html
    assert expected_title in html
