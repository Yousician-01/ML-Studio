from typing import Literal
from uuid import UUID

from pydantic import BaseModel, JsonValue

from mlstudio.code_draft_schemas import DraftResponse, DraftSave


class CodeRunRequest(DraftSave):
    draft_id: UUID
    request_id: UUID


class CodeRunResponse(BaseModel):
    id: str
    project_id: str
    draft_id: str
    snapshot_id: str
    status: Literal["PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"]
    source_sha256: str
    entrypoint: str
    artifact_directory: str
    configuration: dict
    created_at: str
    started_at: str | None
    finished_at: str | None
    duration_seconds: float | None
    exit_code: int | None
    error: str | None
    source_integrity: Literal["verified", "unavailable_or_corrupt"]
    source: str | None = None


class CodeRunStarted(CodeRunResponse):
    draft: DraftResponse | None = None


class CodeEvaluationResponse(BaseModel):
    status: Literal[
        "pending",
        "execution_incomplete",
        "not_reported",
        "invalid",
        "available",
        "unavailable_or_corrupt",
    ]
    report: dict[str, JsonValue] | None
