"""Allowlisted operational jobs for the internal ChatGPT app."""

from __future__ import annotations

from dataclasses import dataclass


class JobValidationError(ValueError):
    """Raised when a requested job is not allowed."""


@dataclass(frozen=True)
class JobRequest:
    tool_name: str
    operation: str
    command: list[str]
    read_only: bool


_DIAGNOSTIC_JOBS: dict[str, list[str]] = {
    "readiness_check": ["python", "-m", "app.chatgpt_app.job_runner", "readiness_check"],
    "rag_benchmark_quick": ["python", "-m", "app.chatgpt_app.job_runner", "rag_benchmark_quick"],
}

_CORPUS_JOBS: dict[str, list[str]] = {
    "sfs_update": ["python", "-m", "app.chatgpt_app.job_runner", "sfs_update"],
    "harvest_source": ["python", "-m", "app.chatgpt_app.job_runner", "harvest_source"],
}


def resolve_job_request(
    *,
    tool_name: str,
    operation: str,
    confirm: bool = False,
) -> JobRequest:
    """Resolve an allowlisted job request into a concrete command."""
    if tool_name == "run_diagnostic_job":
        command = _DIAGNOSTIC_JOBS.get(operation)
        if not command:
            raise JobValidationError(f"Unsupported operation: {operation}")
        return JobRequest(
            tool_name=tool_name,
            operation=operation,
            command=command,
            read_only=True,
        )

    if tool_name == "run_corpus_operation":
        if not confirm:
            raise JobValidationError("Mutating corpus operations require confirm=true")
        command = _CORPUS_JOBS.get(operation)
        if not command:
            raise JobValidationError(f"Unsupported operation: {operation}")
        return JobRequest(
            tool_name=tool_name,
            operation=operation,
            command=command,
            read_only=False,
        )

    raise JobValidationError(f"Unsupported tool: {tool_name}")
