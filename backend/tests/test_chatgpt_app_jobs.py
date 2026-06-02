import pytest


def test_resolve_diagnostic_job_is_allowlisted_and_read_only():
    from app.chatgpt_app.jobs import resolve_job_request

    job = resolve_job_request(tool_name="run_diagnostic_job", operation="readiness_check")

    assert job.tool_name == "run_diagnostic_job"
    assert job.operation == "readiness_check"
    assert job.read_only is True
    assert job.command[:2] == ["python", "-m"]


def test_resolve_corpus_job_requires_explicit_confirmation():
    from app.chatgpt_app.jobs import JobValidationError, resolve_job_request

    with pytest.raises(JobValidationError, match="confirm=true"):
        resolve_job_request(tool_name="run_corpus_operation", operation="sfs_update")


def test_resolve_corpus_job_rejects_unknown_operations():
    from app.chatgpt_app.jobs import JobValidationError, resolve_job_request

    with pytest.raises(JobValidationError, match="Unsupported operation"):
        resolve_job_request(
            tool_name="run_corpus_operation",
            operation="drop_everything",
            confirm=True,
        )


def test_resolve_corpus_job_rejects_legacy_reindex_operation():
    from app.chatgpt_app.jobs import JobValidationError, resolve_job_request

    with pytest.raises(JobValidationError, match="Unsupported operation"):
        resolve_job_request(
            tool_name="run_corpus_operation",
            operation="reindex_corpus",
            confirm=True,
        )
