from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

SemanticType = Literal[
    "continuous", "categorical", "binary", "datetime", "identifier", "text", "unknown"
]


class LosslessInteger(BaseModel):
    value_type: Literal["integer"] = "integer"
    value: str = Field(pattern=r"^-?(0|[1-9][0-9]*)$")


Scalar = str | bool | int | float | LosslessInteger | None
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Context = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectCreate(InputModel):
    name: Name
    problem_statement: Context
    description: Annotated[str, Field(max_length=10000)] | None = None
    success_context: Annotated[str, Field(max_length=10000)] | None = None


class ProjectPatch(InputModel):
    name: Name | None = None
    problem_statement: Context | None = None
    description: Annotated[str, Field(max_length=10000)] | None = None
    success_context: Annotated[str, Field(max_length=10000)] | None = None

    @model_validator(mode="after")
    def required_values(self):
        for field in ("name", "problem_statement"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class ProjectResponse(ProjectCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    ml_objective: Literal["binary_classification"]
    created_at: str
    updated_at: str
    active_dataset_id: str | None
    target_column: str | None
    revision: int


class ColumnResponse(BaseModel):
    name: str
    source_order: int
    physical_dtype: str
    missing_count: int
    unique_count: int
    inferred_semantic_type: SemanticType
    semantic_override: SemanticType | None
    effective_semantic_type: SemanticType
    role: Literal["feature", "target", "excluded"]


class DatasetResponse(BaseModel):
    id: str
    revision: int
    project_id: str
    original_filename: str
    format: Literal["csv"]
    created_at: str
    fingerprint: str
    size_bytes: int
    row_count: int
    column_count: int
    missing_cells: int
    duplicate_rows: int
    columns: list[ColumnResponse]
    target_column: str | None
    target_classes: list[Scalar]
    preview: list[list[Scalar]]
    preview_limit: int


class DatasetPatch(InputModel):
    dataset_id: str
    revision: int
    semantic_overrides: dict[str, SemanticType | None] = Field(default_factory=dict)
    target_column: str | None = None
