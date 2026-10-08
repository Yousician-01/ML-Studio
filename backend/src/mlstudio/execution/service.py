"""Fresh generation, immutable publication, and a revision-guarded Run commit."""

import shutil
from importlib.metadata import version
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select, update

from mlstudio.codegen.csv_runtime import parse_csv_bytes
from mlstudio.codegen.plan import resolve
from mlstudio.codegen.render import generate
from mlstudio.codegen.workload_runtime import read_verified_bytes
from mlstudio.execution.artifacts import (
    bounded_read,
    canonical,
    digest,
    run_directory,
    safe_path,
    strict_json,
    sync_directory,
    verify,
    write_new,
)
from mlstudio.execution.schemas import Manifest, RunResponse
from mlstudio.models import Project, Run, utc_now
from mlstudio.pipeline_schemas import PipelineIR
from mlstudio.services.artifacts import verified_source
from mlstudio.services.pipelines import snapshot
from mlstudio.services.source import DomainError


def existing(session, project_id, body):
    run = session.scalar(
        select(Run).where(Run.project_id == project_id, Run.request_id == str(body.request_id))
    )
    if run and (run.revision, run.source_sha256, run.plan_sha256) != (
        body.expected_revision,
        body.expected_source_sha256,
        body.expected_plan_sha256,
    ):
        raise DomainError("Request ID was already used with different execution inputs.", 409)
    return run


def create(session, project_id, body, coordinator):
    if run := existing(session, project_id, body):
        return run
    lease = coordinator.reserve()
    staged = None
    committed = False
    try:
        project, dataset = snapshot(session, project_id)
        if project.revision != body.expected_revision:
            raise DomainError("Project changed. Refresh Code before executing.", 409)
        if dataset is None:
            raise DomainError("An execution-ready Dataset and Pipeline are required.", 422)
        settings = coordinator.settings
        try:
            ir = PipelineIR.model_validate(project.working_pipeline)
            source_path = verified_source(settings.home, dataset)
            frame = parse_csv_bytes(
                read_verified_bytes(source_path, dataset.fingerprint, dataset.size_bytes)
            )
            plan, issues = resolve(ir, dataset, project.target_column, frame)
            if plan is None:
                raise DomainError("Pipeline is not ready. Review Prepare, Train and Code.", 422)
            try:
                source = generate(plan).encode("utf-8")
            except Exception as error:
                raise DomainError(
                    "Code generation failed; no execution attempt was created.", 500
                ) from error
        except (ValidationError, ValueError, OSError, KeyError, TypeError):
            raise DomainError(
                "Execution inputs could not be validated. Review Data and Code.", 422
            ) from None
        ir_bytes = canonical(project.working_pipeline)
        plan_data = plan.model_dump(mode="json")
        plan_bytes = canonical(plan_data)
        if (digest(source), digest(plan_bytes)) != (
            body.expected_source_sha256,
            body.expected_plan_sha256,
        ):
            raise DomainError(
                "Generated source or plan changed. Refresh Code before executing.", 409
            )
        run_id, created_at = str(uuid4()), utc_now()
        directory = run_directory(settings.home, project_id, run_id)
        staged = safe_path(settings.home, f".run-staging/{run_id}")
        if shutil.disk_usage(settings.home).free < settings.run_disk_reserve_bytes + len(
            source
        ) + len(ir_bytes) + len(plan_bytes):
            raise DomainError("Insufficient workspace disk space to prepare execution.", 503)
        staged.mkdir(parents=True)
        inputs = {}
        for name, data in {
            "pipeline_ir.json": ir_bytes,
            "execution_plan.json": plan_bytes,
            "generated_run.py": source,
        }.items():
            write_new(staged / name, data)
            inputs[name] = {
                "path": (directory / name).relative_to(settings.home).as_posix(),
                "sha256": digest(data),
                "size_bytes": len(data),
            }
        manifest = Manifest(
            run_id=run_id,
            project_id=project_id,
            dataset_id=dataset.id,
            revision=project.revision,
            created_at=created_at,
            dataset={
                "path": dataset.source_relative_path,
                "sha256": dataset.fingerprint,
                "size_bytes": dataset.size_bytes,
            },
            inputs=inputs,
            provenance={
                "mlstudio": version("mlstudio"),
                "executor": "local-subprocess-v1",
                "generator": plan.generator,
                "python": plan.implementation.python,
                **plan.implementation.libraries,
            },
            population={
                "source": len(frame),
                "eligible": int(frame[plan.target.column].notna().sum()),
            },
        ).model_dump(mode="json")
        manifest_bytes = canonical(manifest)
        write_new(staged / "package.json", manifest_bytes)
        artifacts = {
            **inputs,
            "package.json": {
                "path": (directory / "package.json").relative_to(settings.home).as_posix(),
                "sha256": digest(manifest_bytes),
                "size_bytes": len(manifest_bytes),
            },
        }
        dataset_id = dataset.id
        summary = {
            "model": plan_data["model"],
            "split": plan_data["split"],
            "target": plan_data["target"],
            "dataset_fingerprint": dataset.fingerprint,
        }
        session.rollback()  # End the read transaction before acquiring a short write lock.
        sequence = session.scalar(
            update(Project)
            .where(Project.id == project_id, Project.revision == body.expected_revision)
            .values(next_run_sequence=Project.next_run_sequence + 1)
            .returning(Project.next_run_sequence)
        )
        if sequence is None:
            raise DomainError("Project changed during package preparation. Refresh Code.", 409)
        if run := existing(session, project_id, body):
            session.rollback()
            return run
        directory.parent.mkdir(parents=True, exist_ok=True)
        sync_directory(staged)
        staged.rename(directory)
        staged = None
        sync_directory(directory.parent)
        for artifact in artifacts.values():
            verify(settings.home, artifact)
        run = Run(
            id=run_id,
            project_id=project_id,
            dataset_id=dataset_id,
            sequence=sequence - 1,
            request_id=str(body.request_id),
            revision=body.expected_revision,
            source_sha256=body.expected_source_sha256,
            plan_sha256=body.expected_plan_sha256,
            state="CREATED",
            created_at=created_at,
            manifest=manifest,
            artifacts=artifacts,
            summary=summary,
            result=None,
            failure=None,
        )
        session.add(run)
        session.commit()
        committed = True
        coordinator.submit(run.id, lease)
        lease = None
        return run
    except ValueError as error:
        raise DomainError("Execution package integrity could not be established.", 503) from error
    finally:
        if not committed:
            session.rollback()
        if staged is not None:
            # Only our unique, unpublished staging directory is removed.
            shutil.rmtree(staged, ignore_errors=True)
        if lease is not None:
            coordinator.release(lease)


def response(run, home, *, detail=False):
    artifacts = {}
    for name, ref in run.artifacts.items():
        try:
            verify(home, ref)
            integrity = "verified"
        except FileNotFoundError:
            integrity = "missing"
        except (ValueError, OSError):
            integrity = "unavailable_or_corrupt"
        artifacts[name] = {
            "size_bytes": ref["size_bytes"],
            "sha256": ref["sha256"],
            "integrity": integrity,
        }
    snapshots = {}
    if detail:
        try:
            for key, name in (
                ("pipeline_ir", "pipeline_ir.json"),
                ("execution_plan", "execution_plan.json"),
            ):
                ref = run.artifacts[name]
                snapshots[key] = strict_json(bounded_read(verify(home, ref), ref["size_bytes"]))
        except (OSError, ValueError):
            snapshots = {
                "snapshot_error": (
                    "Frozen configuration is missing or corrupt. "
                    "It will not be reconstructed from current state."
                )
            }
    return RunResponse(
        **{
            name: getattr(run, name)
            for name in (
                "id",
                "project_id",
                "dataset_id",
                "sequence",
                "revision",
                "request_id",
                "state",
                "created_at",
                "started_at",
                "finished_at",
                "summary",
                "result",
                "failure",
                "tracking_status",
                "mlflow_run_id",
                "tracking_error",
                "tracking_updated_at",
            )
        },
        provenance=run.manifest["provenance"],
        artifacts=artifacts,
        **snapshots,
    )


def historical_source(run, home):
    try:
        path = verify(home, run.artifacts["generated_run.py"])
        data = bounded_read(path, run.artifacts["generated_run.py"]["size_bytes"])
        if digest(data) != run.source_sha256:
            raise ValueError("Historical source changed during read.")
        return data.decode("utf-8")
    except (OSError, ValueError, KeyError):
        raise DomainError(
            "Historical source is missing or corrupt; it cannot be regenerated.", 409
        ) from None
