"""Versioned package and API contracts, separate from persistence models."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class RunRequest(Contract):
    request_id: UUID
    expected_revision: int = Field(gt=0, strict=True)
    expected_source_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    expected_plan_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class Artifact(Contract):
    path: str
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)


class Manifest(Contract):
    version: Literal["mlstudio-package-v1"] = "mlstudio-package-v1"
    run_id: UUID
    project_id: UUID
    dataset_id: UUID
    revision: int
    created_at: str
    dataset: Artifact
    inputs: dict[str, Artifact]
    provenance: dict[str, str]
    population: dict[str, int]


class RunResponse(Contract):
    id: str
    project_id: str
    dataset_id: str
    sequence: int
    revision: int
    request_id: str
    state: Literal["CREATED", "RUNNING", "SUCCEEDED", "FAILED"]
    created_at: str
    started_at: str | None
    finished_at: str | None
    summary: dict
    result: dict | None
    failure: dict | None
    provenance: dict[str, str]
    artifacts: dict[str, dict]
    tracking_status: Literal["NOT_ATTEMPTED", "SYNCHRONIZED", "FAILED"]
    mlflow_run_id: str | None
    tracking_error: str | None
    tracking_updated_at: str | None
    pipeline_ir: dict | None = None
    execution_plan: dict | None = None
    snapshot_error: str | None = None


class ExecutionCapacity(Contract):
    occupied: bool
    recovery_required: bool


class RunList(Contract):
    items: list[RunResponse]
    offset: int
    limit: int
    total: int


class HistoricalCode(Contract):
    run_id: str
    source: str
    source_sha256: str
    filename: Literal["generated_run.py"] = "generated_run.py"
