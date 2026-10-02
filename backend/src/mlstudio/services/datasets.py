import os
import tempfile
from pathlib import Path

import pandas as pd
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from mlstudio.core.config import Settings
from mlstudio.models import Dataset, Project, new_id, utc_now
from mlstudio.schemas import DatasetPatch, DatasetResponse
from mlstudio.services.artifacts import fingerprint, source_path, verified_source
from mlstudio.services.pipeline_state import column_role, initialize, reconcile_target
from mlstudio.services.source import (
    PREVIEW_LIMIT,
    DomainError,
    describe_columns,
    infer_semantic,
    json_scalar,
    parse_source,
    target_classes,
)


def current_dataset(session: Session, project: Project) -> Dataset:
    dataset = session.get(Dataset, project.active_dataset_id) if project.active_dataset_id else None
    if dataset is None:
        raise DomainError("No Dataset is attached to this Project.", 404)
    return dataset


def dataset_response(dataset: Dataset, project: Project, frame: pd.DataFrame) -> DatasetResponse:
    columns = []
    for column in dataset.columns:
        name = column["name"]
        role = column_role(project, dataset, name)
        columns.append(
            {
                **column,
                "effective_semantic_type": column["semantic_override"]
                or column["inferred_semantic_type"],
                "role": role,
            }
        )
    return DatasetResponse(
        **{
            key: getattr(dataset, key)
            for key in (
                "id",
                "project_id",
                "original_filename",
                "format",
                "created_at",
                "fingerprint",
                "size_bytes",
                "row_count",
                "column_count",
                "missing_cells",
                "duplicate_rows",
            )
        },
        columns=columns,
        revision=project.revision,
        target_column=project.target_column,
        target_classes=target_classes(frame, project.target_column)
        if project.target_column
        else [],
        preview=[
            [json_scalar(value) for value in row]
            for row in frame.head(PREVIEW_LIMIT).itertuples(index=False, name=None)
        ],
        preview_limit=PREVIEW_LIMIT,
    )


def read_dataset(session: Session, project: Project, settings: Settings) -> DatasetResponse:
    # One statement reads configuration and its revision from the same DB snapshot.
    snapshot = session.execute(
        select(Project, Dataset)
        .join(Dataset, Dataset.id == Project.active_dataset_id)
        .where(Project.id == project.id)
        .execution_options(populate_existing=True)
    ).one_or_none()
    if snapshot is None:
        raise DomainError("No Dataset is attached to this Project.", 404)
    project, dataset = snapshot
    return dataset_response(dataset, project, parse_source(verified_source(settings.home, dataset)))


def ingest(
    session: Session,
    project: Project,
    upload: UploadFile,
    expected_dataset_id: str | None,
    settings: Settings,
) -> DatasetResponse:
    if expected_dataset_id != project.active_dataset_id:
        raise DomainError(
            "Dataset changed or replacement was not confirmed. Reload and try again.", 409
        )
    staging = settings.home / ".ingestion"
    staging.mkdir(exist_ok=True)
    if staging.resolve() != staging.absolute():
        raise DomainError("Managed staging location is invalid.", 409)
    managed: Path | None = None
    committed = False
    try:
        with tempfile.NamedTemporaryFile(dir=staging, suffix=".csv", delete=False) as output:
            temporary = Path(output.name)
            size = 0
            while chunk := upload.file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_csv_upload_bytes:
                    raise DomainError(
                        f"CSV exceeds the {settings.max_csv_upload_bytes} byte upload limit.", 413
                    )
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if size == 0:
            raise DomainError("The uploaded file is empty.")
        digest = fingerprint(temporary)
        frame = parse_source(temporary)
        columns = describe_columns(frame)
        dataset_id = new_id()
        destination = source_path(settings.home, project.id, dataset_id)
        destination.parent.mkdir(parents=True, exist_ok=False)
        managed = destination  # Cleanup only an area successfully allocated by this ingestion.
        temporary.rename(managed)
        dataset = Dataset(
            id=dataset_id,
            project_id=project.id,
            original_filename=upload.filename or "upload.csv",
            format="csv",
            created_at=utc_now(),
            fingerprint=digest,
            source_relative_path=managed.relative_to(settings.home).as_posix(),
            size_bytes=size,
            row_count=len(frame),
            column_count=len(frame.columns),
            missing_cells=int(frame.isna().sum().sum()),
            duplicate_rows=int(frame.duplicated().sum()),
            columns=columns,
            pandas_version=pd.__version__,
        )
        session.add(dataset)
        session.flush()  # Source and metadata exist before switching the active reference.
        project.active_dataset_id = dataset.id
        project.target_column = None
        if project.working_pipeline["dataset"] is None:
            project.working_pipeline = initialize(dataset, None)
        project.updated_at = utc_now()
        session.flush()  # Resolve the revision represented by the returned snapshot.
        result = dataset_response(dataset, project, frame)
        session.commit()  # Optimistic Project revision prevents concurrent replacements.
        committed = True
        return result
    finally:
        if "temporary" in locals():
            temporary.unlink(missing_ok=True)
        if not committed:
            session.rollback()
            if managed is not None:
                managed.unlink(missing_ok=True)
                if managed.parent.exists():
                    managed.parent.rmdir()
        # A process crash can leave an unreferenced artifact; never delete retained sources.


def configure(
    session: Session, project: Project, change: DatasetPatch, settings: Settings
) -> DatasetResponse:
    dataset = current_dataset(session, project)
    if change.dataset_id != dataset.id or change.revision != project.revision:
        raise DomainError("Project changed. Reload before saving Dataset configuration.", 409)
    frame = parse_source(verified_source(settings.home, dataset))
    names = {column["name"] for column in dataset.columns}
    if not set(change.semantic_overrides).issubset(names):
        raise DomainError("Semantic overrides must refer to active Dataset columns.")
    if "target_column" in change.model_fields_set:
        if change.target_column is not None:
            target_classes(frame, change.target_column)
        old_target = project.target_column
        project.target_column = change.target_column
        if old_target != change.target_column:
            reconcile_target(project, dataset, old_target)
    dataset.columns = [
        {
            **column,
            **(
                {
                    "inferred_semantic_type": infer_semantic(frame[column["name"]]),
                    "inference_version": "semantic-v2",
                }
                if change.refresh_inference
                else {}
            ),
            "semantic_override": change.semantic_overrides.get(
                column["name"], column["semantic_override"]
            ),
        }
        for column in dataset.columns
    ]
    project.updated_at = utc_now()
    session.flush()
    result = dataset_response(dataset, project, frame)
    session.commit()
    return result
