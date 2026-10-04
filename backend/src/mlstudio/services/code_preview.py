"""Side-effect-free current Code view. Historical Run source is a different boundary."""

import hashlib
import json

import pandas as pd
from pydantic import ValidationError
from sqlalchemy import select

from mlstudio.codegen.csv_runtime import parse_csv_bytes
from mlstudio.codegen.plan import resolve
from mlstudio.codegen.render import generate
from mlstudio.codegen.schemas import CodePreview
from mlstudio.codegen.workload_runtime import read_verified_bytes
from mlstudio.models import Project
from mlstudio.pipeline_schemas import PipelineIR, PipelineIssue
from mlstudio.services.artifacts import verified_source
from mlstudio.services.pipelines import snapshot
from mlstudio.services.source import DomainError


def preview(session, project, settings):
    project, dataset = snapshot(session, project.id)
    identity = dict(
        project_id=project.id, revision=project.revision, dataset_id=dataset.id if dataset else None
    )
    try:
        ir = PipelineIR.model_validate(project.working_pipeline)
    except ValidationError:
        return CodePreview(
            **identity,
            ready=False,
            issues=[
                PipelineIssue(
                    scope="pipeline",
                    code="persisted_ir_invalid",
                    message="Stored Pipeline configuration or version is unsupported. "
                    "Reset configuration in Prepare before generating code.",
                )
            ],
        )
    try:
        frame = (
            pd.DataFrame()
            if dataset is None
            else parse_csv_bytes(
                read_verified_bytes(
                    verified_source(settings.home, dataset),
                    dataset.fingerprint,
                    dataset.size_bytes,
                )
            )
        )
    except (DomainError, OSError, ValueError):
        return CodePreview(
            **identity,
            ready=False,
            issues=[
                PipelineIssue(
                    scope="pipeline",
                    code="source_unavailable",
                    message="Managed source is missing, corrupt, or unreadable. Restore its bytes "
                    "or upload a replacement in Data; metadata has been preserved.",
                )
            ],
        )
    try:
        plan, issues = resolve(ir, dataset, project.target_column, frame)
    except (ValidationError, KeyError, TypeError, ValueError):
        return CodePreview(
            **identity,
            ready=False,
            issues=[
                PipelineIssue(
                    scope="pipeline",
                    code="context_invalid",
                    message="Dataset interpretation cannot be resolved. Review Data and restore "
                    "the documented library environment.",
                )
            ],
        )
    if plan is None:
        return CodePreview(**identity, ready=False, issues=issues)
    try:
        source = generate(plan)
    except Exception as error:
        # Never return partial source or expose Dataset-controlled exception text.
        raise DomainError(
            "Code generation failed internally. Reload and report the problem.", 500
        ) from error
    latest_revision = session.scalar(select(Project.revision).where(Project.id == project.id))
    if latest_revision != identity["revision"]:
        raise DomainError("Project changed during generation. Refresh Code.", 409)
    canonical = json.dumps(
        plan.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return CodePreview(
        **identity,
        ready=True,
        issues=issues,
        source=source,
        source_sha256="sha256:" + hashlib.sha256(source.encode("utf-8")).hexdigest(),
        plan_sha256="sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        libraries=plan.implementation.libraries,
    )
