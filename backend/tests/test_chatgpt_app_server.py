from fastapi import FastAPI


def test_build_tool_catalog_declares_read_and_write_tools():
    from app.chatgpt_app.server import build_tool_catalog

    catalog = build_tool_catalog()

    assert catalog["query_constitutional_ai"]["annotations"]["readOnlyHint"] is True
    assert catalog["inspect_runtime"]["annotations"]["readOnlyHint"] is True
    assert catalog["inspect_project"]["annotations"]["readOnlyHint"] is True
    assert catalog["run_diagnostic_job"]["annotations"]["readOnlyHint"] is False
    assert catalog["run_corpus_operation"]["annotations"]["readOnlyHint"] is False
    assert catalog["render_query_report"]["meta"]["ui_resource"] == "ui://widget/operator.html"


def test_build_widget_resource_descriptor_contains_chatgpt_metadata():
    from app.chatgpt_app.server import build_widget_resource_descriptor

    resource = build_widget_resource_descriptor()

    assert resource["uri"] == "ui://widget/operator.html"
    assert resource["mime_type"] == "text/html;profile=mcp-app"
    assert resource["meta"]["openai/widgetDescription"]
    assert resource["meta"]["ui"]["csp"]["connectDomains"] == []
    assert resource["meta"]["ui"]["prefersBorder"] is True


def test_mount_chatgpt_app_adds_mcp_route():
    from app.chatgpt_app.server import mount_chatgpt_app

    app = FastAPI()
    mount_chatgpt_app(app)

    mount_paths = {route.path for route in app.routes}
    assert "/mcp" in mount_paths
