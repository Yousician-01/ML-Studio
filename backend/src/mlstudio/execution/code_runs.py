"""Managed single-file Code Runs; shared local process/capture/capacity helpers."""

import os
import platform
import threading
import time
from importlib.metadata import version
from uuid import uuid4

import psutil
from sqlalchemy import select

from mlstudio.code_run_schemas import CodeRunResponse
from mlstudio.execution import process
from mlstudio.execution.artifacts import (
    bounded_read,
    digest,
    reference,
    safe_path,
    verify,
    write_evidence,
    write_new,
)
from mlstudio.execution.results import ExecutionFailure
from mlstudio.models import CodeRun, Dataset, utc_now
from mlstudio.services import code_drafts
from mlstudio.services.artifacts import verified_source
from mlstudio.services.source import DomainError

ACTIVE = ("PENDING", "RUNNING")


def directory(settings, run):
    expected = f"projects/{run.project_id}/code-runs/{run.id}"
    if run.artifact_directory != expected:
        raise ValueError("Invalid Code Run location")
    return safe_path(settings.home, expected)


def response(settings, run, *, include_source=True):
    integrity = "unavailable_or_corrupt"
    try:
        source = bounded_read(directory(settings, run) / "source.py", 1048576)
        if digest(source) == run.source_sha256 == digest(run.source.encode()):
            integrity = "verified"
    except (OSError, ValueError):
        pass
    return CodeRunResponse(
        **{
            name: getattr(run, name)
            for name in CodeRunResponse.model_fields
            if name not in {"source_integrity", "source"}
        },
        source=run.source if include_source else None,
        source_integrity=integrity,
    )


def owned(session, project_id, run_id):
    run = session.get(CodeRun, run_id)
    if run is None or run.project_id != project_id:
        raise DomainError("Code Run not found.", 404)
    return run


def logs(settings, run):
    output = {}
    for name in ("stdout", "stderr"):
        path = safe_path(settings.home, f"{run.artifact_directory}/{name}.log")
        data = b""
        try:
            if path.exists():
                from mlstudio.execution.artifacts import regular

                size = regular(path, run.configuration["log_bytes"])
                if run.status not in ACTIVE and name in run.logs:
                    verify(settings.home, run.logs[name]["artifact"])
                with path.open("rb") as stream:
                    stream.seek(max(0, size - 65536))
                    data = stream.read(65536)
                output[name + "_tail_only"] = size > 65536
            output[name] = data.decode("utf-8", errors="replace")
            output[name + "_truncated"] = run.logs.get(name, {}).get("truncated", False)
        except (OSError, ValueError):
            raise DomainError("Code Run logs are unavailable or have changed.", 409) from None
    return output


class CodeExecutor:
    def __init__(self, settings, sessions, coordinator):
        self.settings, self.sessions, self.coordinator = settings, sessions, coordinator
        self.shutdown = threading.Event()
        self.workers = []
        coordinator.code_reconcile = self.reconcile

    def start(self, session, project, body):
        checksum = digest(body.source.encode())
        previous = session.scalar(
            select(CodeRun).where(
                CodeRun.project_id == project.id, CodeRun.request_id == str(body.request_id)
            )
        )
        if previous:
            if (previous.draft_id, previous.submitted_revision, previous.source_sha256) != (
                str(body.draft_id),
                body.revision,
                checksum,
            ):
                raise DomainError(
                    "Request ID was already used with different Code Run inputs.", 409
                )
            current = code_drafts.owned(session, project.id, previous.draft_id)
            saved = (
                code_drafts.response(current)
                if current.revision == previous.configuration["saved_draft_revision"]
                else None
            )
            return {**response(self.settings, previous).model_dump(), "draft": saved}
        if self.shutdown.is_set():
            raise DomainError("The execution service is shutting down.", 503)
        lease = self.coordinator.reserve()
        committed = False
        try:
            draft = code_drafts.writable(session, project.id, str(body.draft_id), body.revision)
            project.updated_at = utc_now()
            draft.source, draft.updated_at = body.source, utc_now()
            session.flush()
            frozen = code_drafts.add_snapshot(session, draft)
            session.flush()
            run_id = str(uuid4())
            relative = f"projects/{project.id}/code-runs/{run_id}"
            root = safe_path(self.settings.home, relative)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            write_new(root / "source.py", body.source.encode())
            write_new(workspace / "main.py", body.source.encode())
            arguments = [
                str(self.settings.code_python_executable),
                "-u",
                "-B",
                "-X",
                "utf8",
                str(workspace / "main.py"),
            ]
            binding = draft.origin_ir.get("dataset")
            dataset_ref = None
            if binding:
                dataset = session.get(Dataset, binding["dataset_id"])
                if (
                    dataset is None
                    or dataset.project_id != project.id
                    or dataset.fingerprint != binding["fingerprint"]
                ):
                    raise DomainError("The originating managed Dataset is unavailable.", 409)
                source_path = verified_source(self.settings.home, dataset)
                dataset_ref = reference(self.settings.home, source_path, dataset.size_bytes)
                if dataset_ref["sha256"] != binding["fingerprint"]:
                    raise DomainError("Originating Dataset bytes changed during preparation.", 409)
                arguments += [
                    "--dataset",
                    str(source_path),
                    "--result",
                    str(workspace / "result.json"),
                    "--model",
                    str(workspace / "model.joblib"),
                ]
            libraries = {}
            if os.path.abspath(self.settings.code_python_executable) == os.path.abspath(
                os.sys.executable
            ):
                libraries = {
                    name: version(name)
                    for name in ("pandas", "numpy", "scikit-learn", "scipy", "joblib")
                }
            configuration = {
                "version": "code-execution-v1",
                "python": str(self.settings.code_python_executable),
                "arguments": arguments,
                "host_python": platform.python_version(),
                "libraries": libraries,
                "environment": process.environment(),
                "dataset": dataset_ref,
                "timeout_seconds": self.settings.run_timeout_seconds,
                "log_bytes": self.settings.run_log_bytes,
                "saved_draft_revision": draft.revision,
            }
            write_evidence(
                root / "execution.json", {"arguments": arguments, "process": None, "children": []}
            )
            run = CodeRun(
                id=run_id,
                project_id=project.id,
                draft_id=draft.id,
                snapshot_id=frozen.id,
                request_id=str(body.request_id),
                submitted_revision=body.revision,
                source=body.source,
                source_sha256=checksum,
                entrypoint="main.py",
                artifact_directory=relative,
                configuration=configuration,
            )
            session.add(run)
            session.commit()
            committed = True
            try:
                worker = threading.Thread(
                    target=self.execute,
                    args=(run.id, lease),
                    name="mlstudio-code-run",
                    daemon=False,
                )
                self.workers = [item for item in self.workers if item.is_alive()]
                self.workers.append(worker)
                worker.start()
            except Exception:
                self.finish(run.id, "FAILED", None, 0, "Execution worker could not start.", {})
                self.coordinator.release(lease)
            return {
                **response(self.settings, run).model_dump(),
                "draft": code_drafts.response(draft),
            }
        finally:
            if not committed:
                session.rollback()
                self.coordinator.release(lease)

    def finish(self, run_id, status, exit_code, duration, error, evidence):
        with self.sessions() as session:
            row = session.get(CodeRun, run_id)
            if row.status in ACTIVE:
                row.status, row.finished_at = status, utc_now()
                row.exit_code, row.duration_seconds = exit_code, duration
                row.error, row.logs = error, evidence
                session.commit()

    def execute(self, run_id, lease):
        child, owner, captures, descendants = None, None, [], {}
        started = time.monotonic()
        status, error, exit_code = "FAILED", "Python execution could not start.", None
        clean = True
        evidence = {}
        try:
            with self.sessions() as session:
                run = session.get(CodeRun, run_id)
                session.expunge(run)
            root = directory(self.settings, run)
            if digest(bounded_read(root / "workspace" / "main.py", 1048576)) != run.source_sha256:
                raise ValueError("Execution source changed")
            if run.configuration["dataset"]:
                verify(self.settings.home, run.configuration["dataset"])
            journal = {"arguments": run.configuration["arguments"], "process": None, "children": []}
            if run.cancel_requested or self.shutdown.is_set():
                status, error = "CANCELLED", "Execution cancelled before launch."
            else:
                child = process.launch(
                    run.configuration["arguments"],
                    root / "workspace",
                    env=run.configuration["environment"],
                )
                journal["process"] = process.identity(child)
                if journal["process"]["created"] is not None:
                    try:
                        owner = psutil.Process(child.pid)
                        if owner.create_time() != journal["process"]["created"]:
                            raise ExecutionFailure("ownership_uncertain")
                    except psutil.NoSuchProcess:
                        owner = None
                write_evidence(root / "execution.json", journal)
                for name, pipe in (("stdout", child.stdout), ("stderr", child.stderr)):
                    # Raw pipe reads return available bytes immediately; Capture owns
                    # bounded storage/draining without a second logging subsystem.
                    capture = process.Capture(
                        getattr(pipe, "raw", pipe),
                        root / f"{name}.log",
                        run.configuration["log_bytes"],
                        live=True,
                    )
                    captures.append((name, capture))
                    capture.thread.start()
                with self.sessions() as session:
                    row = session.get(CodeRun, run_id)
                    row.status, row.started_at = "RUNNING", utc_now()
                    session.commit()
                status, error = "COMPLETED", None
                while child.poll() is None:
                    if owner:
                        try:
                            for descendant in owner.children(recursive=True):
                                if descendant.pid not in descendants:
                                    descendants[descendant.pid] = descendant
                                    journal["children"].append(
                                        {
                                            "pid": descendant.pid,
                                            "created": descendant.create_time(),
                                            "arguments": descendant.cmdline(),
                                        }
                                    )
                                    write_evidence(root / "execution.json", journal)
                        except psutil.NoSuchProcess:
                            pass
                    with self.sessions() as session:
                        cancelled = session.get(CodeRun, run_id).cancel_requested
                    if cancelled or self.shutdown.is_set():
                        status, error = "CANCELLED", "Execution cancelled."
                        break
                    if time.monotonic() - started >= run.configuration["timeout_seconds"]:
                        status, error = "FAILED", "Execution exceeded its configured timeout."
                        break
                    if any(capture.failed.is_set() for _, capture in captures):
                        status, error = "FAILED", "Captured output could not be stored."
                        break
                    self.shutdown.wait(0.05)
        except Exception as failure:
            status, error = (
                "FAILED",
                "Execution inputs, process or storage could not be verified "
                f"({type(failure).__name__}).",
            )
        finally:
            try:
                if child:
                    if child.poll() is None:
                        if owner is None:
                            raise ExecutionFailure("ownership_uncertain")
                        process.stop_tree(owner, self.settings.run_termination_grace_seconds)
                    for descendant in descendants.values():
                        process.stop_tree(descendant, self.settings.run_termination_grace_seconds)
                    exit_code = child.wait()
                    for name, capture in captures:
                        capture.thread.join(timeout=self.settings.run_termination_grace_seconds)
                        if capture.thread.is_alive():
                            raise ExecutionFailure("ownership_uncertain")
                        if capture.failed.is_set():
                            status, error = "FAILED", "Captured output storage failed."
                        evidence[name] = {
                            "artifact": reference(
                                self.settings.home,
                                root / f"{name}.log",
                                run.configuration["log_bytes"],
                            ),
                            "truncated": capture.truncated,
                        }
                    if status == "COMPLETED" and exit_code != 0:
                        status, error = "FAILED", "Python exited with a nonzero status."
                self.finish(
                    run_id, status, exit_code, max(0, time.monotonic() - started), error, evidence
                )
            except Exception:
                clean = False
                self.coordinator.blocked = True
                self.coordinator.held_lease = lease
                with self.sessions() as session:
                    row = session.get(CodeRun, run_id)
                    row.error = "Execution cleanup requires attention; capacity remains blocked."
                    session.commit()
            if clean:
                self.coordinator.release(lease)
            else:
                self.coordinator.guard.release()

    def reconcile(self):
        """Called under the existing shared lease before visual or Code admission."""
        with self.sessions() as session:
            rows = session.scalars(select(CodeRun).where(CodeRun.status.in_(ACTIVE))).all()
            for run in rows:
                root = directory(self.settings, run)
                from mlstudio.execution.artifacts import strict_json

                journal = strict_json(bounded_read(root / "execution.json", 1048576))
                arguments = run.configuration["arguments"]
                if journal.get("arguments") != arguments:
                    raise ExecutionFailure("ownership_uncertain")
                identities = journal.get("children", [])
                if journal.get("process"):
                    identities = [*identities, {**journal["process"], "arguments": arguments}]
                for identity in identities:
                    owned_child = process.owned_process(identity, identity["arguments"])
                    if owned_child:
                        process.stop_tree(owned_child, self.settings.run_termination_grace_seconds)
                # Cover the launch-to-PID-journal crash gap with exact unique argv.
                for candidate in psutil.process_iter(["cmdline"]):
                    if candidate.info["cmdline"] == arguments:
                        fresh = psutil.Process(candidate.pid)
                        if fresh.cmdline() == arguments:
                            process.stop_tree(fresh, self.settings.run_termination_grace_seconds)
                run.status, run.finished_at = "FAILED", utc_now()
                run.error = "Backend execution was interrupted; this Code Run will not resume."
                run.duration_seconds = None
            session.commit()

    def close(self):
        self.shutdown.set()
        for worker in self.workers:
            worker.join()
