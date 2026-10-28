"""Text-only Code Mode contracts. No filesystem or execution parameters."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mlstudio.schemas import InputModel

Digest = Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]
Source = Annotated[str, Field(max_length=1048576)]


class DraftCreate(InputModel):
    revision: int = Field(strict=True, ge=1)
    source_sha256: Digest
    plan_sha256: Digest


class DraftSave(InputModel):
    revision: int = Field(strict=True, ge=1)
    source: Source

    @field_validator("source")
    @classmethod
    def supported_source(cls, source):
        try:
            if "\x00" in source or len(source.encode("utf-8")) > 1048576:
                raise ValueError()
        except (UnicodeError, ValueError):
            raise ValueError(
                "Python text must be UTF-8, at most 1 MiB, without NUL characters."
            ) from None
        return source


class DraftExit(DraftSave):
    action: Literal["discard", "save_snapshot"]
    source: Source = ""

    @model_validator(mode="after")
    def explicit_snapshot_source(self):
        if self.action == "save_snapshot" and "source" not in self.model_fields_set:
            raise ValueError("Supply the explicit Python text to save a code snapshot.")
        return self


class DraftResponse(BaseModel):
    id: str
    project_id: str
    origin_revision: int
    origin_ir: dict
    baseline_source: str
    baseline_sha256: str
    plan_sha256: str
    source: str
    status: Literal["active", "archived", "discarded"]
    created_at: str
    updated_at: str
    revision: int
    modified: bool


class SnapshotSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    draft_id: str
    source_sha256: str
    created_at: str


class SnapshotResponse(SnapshotSummary):
    source: str


class DraftSummary(BaseModel):
    id: str
    status: Literal["active", "archived", "discarded"]
    origin_revision: int
    created_at: str
    updated_at: str


class SnapshotSaved(BaseModel):
    draft: DraftResponse
    snapshot: SnapshotResponse


class ReportingProposal(BaseModel):
    status: Literal["ready", "present", "manual"]
    revision: int
    proposed_source: str | None
    diff: str
    example: str
    message: str
