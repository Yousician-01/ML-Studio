"""Lifespan-owned execution and conservative restart reconciliation. No queue."""

import os
import threading
from uuid import UUID, uuid4

import psutil
from sqlalchemy import select

from mlstudio.db.revision import migration_message
from mlstudio.execution import process, tracking
from mlstudio.execution.artifacts import (
    bounded_read,
    reference,
    regular,
    run_directory,
    safe_path,
    strict_json,
    sync_directory,
    verify,
    write_evidence,
)
from mlstudio.execution.results import ExecutionFailure, failure_stage, validate_result
from mlstudio.models import Run, utc_now
from mlstudio.services.source import DomainError

ACTIVE = ("CREATED", "RUNNING")


class Coordinator:
    def __init__(self, settings, sessions):
        self.settings, self.sessions = settings, sessions
        self.guard = threading.Lock()
        self.shutdown = threading.Event()
        self.worker = None
        self.workers = []
        self.blocked = False
        self.held_lease = None

    def reserve(self):
        if self.shutdown.is_set() or self.blocked or not self.guard.acquire(blocking=False):
            raise DomainError("Execution capacity is occupied or requires recovery.", 409)
        try:
            lease = process.WorkspaceLease(self.settings.home)
        except (OSError, ValueError):
            self.guard.release()
            raise DomainError(
                "Another application owns workspace execution capacity.", 409
            ) from None
        try:
            self.reconcile()
        except Exception:
            self.blocked = True
            self.held_lease = lease
            self.guard.release()
            raise DomainError(
                "Execution recovery requires attention; no new attempt was started.", 503
            ) from None
        return lease

    def release(self, lease):
        lease.close()
        self.guard.release()

    def startup(self):
        with self.sessions() as session:
            if migration_message(session.connection()):
                return
        try:
            lease = self.reserve()
        except DomainError:
            return
        self.release(lease)
        tracking.reconcile(self.settings, self.sessions)

    def close(self):
        self.shutdown.set()
        for worker in self.workers:
            worker.join()
        if self.held_lease:
            self.held_lease.close()

    def submit(self, run_id, lease):
        try:
            self.worker = threading.Thread(
                target=self.execute, args=(run_id, lease), name="mlstudio-execution", daemon=False
            )
            self.worker.start()
            self.workers = [worker for worker in self.workers if worker.is_alive()]
            self.workers.append(self.worker)
        except Exception:
            self.worker = None
            self.finish(
                run_id,
                failure={
                    "code": "launch_failure",
                    "stage": "launch",
                    "message": "Execution could not be started.",
                },
            )
            self.release(lease)
            tracking.synchronize(self.settings, self.sessions, run_id)

    def finish(self, run_id, *, result=None, artifacts=None, failure=None, started_at=None):
        with self.sessions() as session:
            run = session.get(Run, run_id)
            if run.state not in ACTIVE:
                return
            run.state = "FAILED" if failure else "SUCCEEDED"
            if started_at is not None and run.started_at is None:
                run.started_at = started_at
            run.finished_at = utc_now()
            run.failure, run.result = failure, result
            if artifacts:
                run.artifacts = {**run.artifacts, **artifacts}
            session.commit()

    def execute(self, run_id, lease):
        child = None
        ownership = None
        captures = []
        evidence = {"version": "mlstudio-execution-v1", "process": None}
        directory = None
        failure = None
        result = None
        outputs = {}
        try:
            with self.sessions() as session:
                run = session.get(Run, run_id)
                session.expunge(run)
            directory = run_directory(self.settings.home, run.project_id, run.id)
            try:
                for artifact in run.artifacts.values():
                    verify(self.settings.home, artifact)
            except (OSError, ValueError):
                raise ExecutionFailure("package_corrupt", "launch") from None
            if (
                strict_json(
                    bounded_read(
                        directory / "package.json", run.artifacts["package.json"]["size_bytes"]
                    )
                )
                != run.manifest
            ):
                raise ExecutionFailure("package_corrupt", "launch")
            plan = strict_json(
                bounded_read(
                    directory / "execution_plan.json",
                    run.artifacts["execution_plan.json"]["size_bytes"],
                )
            )
            try:
                dataset = verify(self.settings.home, run.manifest["dataset"])
            except (OSError, ValueError):
                raise ExecutionFailure("dataset_mismatch", "data_loading") from None
            (directory / ".pending").mkdir()
            arguments = process.command(directory, dataset)
            # Persist intended command before launch so a crash in the launch/journal gap
            # can be reconciled by exact unique script/argument identity, never PID alone.
            evidence["arguments"] = arguments
            write_evidence(directory / "execution.json", evidence)
            try:
                child = process.launch(arguments, directory)
            except OSError:
                raise ExecutionFailure("launch_failure", "launch") from None
            evidence["started_at"] = utc_now()
            evidence["process"] = process.identity(child)
            if evidence["process"]["created"] is not None:
                try:
                    ownership = psutil.Process(child.pid)
                    if ownership.create_time() != evidence["process"]["created"]:
                        raise ExecutionFailure("ownership_uncertain", "launch")
                except psutil.NoSuchProcess:
                    ownership = None
            for name, pipe in (("stdout", child.stdout), ("stderr", child.stderr)):
                capture = process.Capture(
                    pipe, directory / f"{name}.log", self.settings.run_log_bytes
                )
                captures.append(capture)
                capture.thread.start()
            write_evidence(directory / "execution.json", evidence)
            with self.sessions() as session:
                active = session.get(Run, run_id)
                active.state, active.started_at = "RUNNING", evidence["started_at"]
                session.commit()
            exit_code = process.wait(child, captures, self.settings, self.shutdown, ownership)
            evidence["exit_code"] = exit_code
            if exit_code != 0:
                raise ExecutionFailure(
                    "nonzero_exit",
                    failure_stage(
                        directory / ".pending/result.json", self.settings.run_result_bytes
                    ),
                )
            for artifact in run.artifacts.values():
                verify(self.settings.home, artifact)
            verify(self.settings.home, run.manifest["dataset"])
            result = validate_result(
                directory / ".pending/result.json",
                self.settings.run_result_bytes,
                plan,
                run.manifest["population"],
            )
            model = directory / ".pending/model.joblib"
            try:
                if regular(model, self.settings.run_model_bytes) == 0:
                    raise ValueError()
            except FileNotFoundError:
                raise ExecutionFailure("model_missing", "model") from None
            except (OSError, ValueError):
                raise ExecutionFailure("model_invalid", "model") from None
            for name, limit in (
                ("result.json", self.settings.run_result_bytes),
                ("model.joblib", self.settings.run_model_bytes),
            ):
                provisional = directory / ".pending" / name
                with provisional.open("rb+") as stream:
                    os.fsync(stream.fileno())
                ref = reference(self.settings.home, provisional, limit)
                final = directory / name
                provisional.rename(final)
                ref["path"] = final.relative_to(self.settings.home).as_posix()
                verify(self.settings.home, ref)
                outputs[name] = ref
            sync_directory(directory)
        except ExecutionFailure as error:
            failure = {
                "code": error.code,
                "stage": error.stage,
                "message": "Execution did not complete successfully. "
                "Diagnostic evidence is retained locally.",
            }
        except Exception:
            failure = {
                "code": "artifact_finalization",
                "stage": "execution",
                "message": "Execution evidence could not be validated or persisted.",
            }
        finally:
            try:
                if child is not None:
                    if child.poll() is None:
                        if ownership is None:
                            raise ExecutionFailure("ownership_uncertain", "cleanup")
                        process.stop_tree(ownership, self.settings.run_termination_grace_seconds)
                    child.wait()
                    for capture in captures:
                        capture.thread.join(timeout=self.settings.run_termination_grace_seconds)
                        if capture.thread.is_alive():
                            raise ExecutionFailure("ownership_uncertain")
                if failure and failure["code"] == "ownership_uncertain":
                    raise ExecutionFailure("ownership_uncertain")
                evidence["finished_at"] = utc_now()
                evidence["logs"] = {
                    name: {
                        "truncated": capture.truncated,
                        "storage_failed": capture.failed.is_set(),
                    }
                    for name, capture in zip(("stdout", "stderr"), captures, strict=False)
                }
                evidence["failure"] = failure
                diagnostics = {}
                if directory is not None:
                    try:
                        write_evidence(directory / "execution.json", evidence)
                        for name in ("execution.json", "stdout.log", "stderr.log"):
                            path = directory / name
                            if path.exists():
                                diagnostics[name] = reference(
                                    self.settings.home,
                                    path,
                                    max(self.settings.run_log_bytes, 1024 * 1024),
                                )
                    except (OSError, ValueError):
                        failure = failure or {
                            "code": "artifact_finalization",
                            "stage": "finalization",
                            "message": "Execution evidence could not be persisted.",
                        }
                self.finish(
                    run_id,
                    result=None if failure else result,
                    artifacts=diagnostics if failure else {**outputs, **diagnostics},
                    failure=failure,
                    started_at=evidence.get("started_at"),
                )
            except Exception:
                # Keep the active record and capacity unavailable. Startup recovery must
                # establish quiescence; a database/storage outage cannot fabricate terminality.
                self.blocked = True
            finally:
                if self.blocked:
                    self.held_lease = lease
                    self.guard.release()
                else:
                    self.release(lease)

        tracking.synchronize(self.settings, self.sessions, run_id)

    def reconcile(self):
        with self.sessions() as session:
            active = list(session.scalars(select(Run).where(Run.state.in_(ACTIVE))))
            known = set(session.scalars(select(Run.id)))
        for run in active:
            directory = run_directory(self.settings.home, run.project_id, run.id)
            arguments = process.command(
                directory, safe_path(self.settings.home, run.manifest["dataset"]["path"])
            )
            journal = directory / "execution.json"
            if journal.exists():
                evidence = strict_json(bounded_read(journal, 1024 * 1024))
                if evidence.get("arguments") != arguments:
                    raise ExecutionFailure("ownership_uncertain", "recovery")
                if evidence.get("process"):
                    owned = process.owned_process(evidence["process"], arguments)
                    if owned:
                        process.stop_tree(owned, self.settings.run_termination_grace_seconds)
            # Covers a crash between Popen and journaling its process creation time.
            # Exact random Run script + complete argv, not a name or PID heuristic.
            for candidate in psutil.process_iter(["pid", "cmdline"]):
                try:
                    if candidate.info["cmdline"] == arguments:
                        # process_iter may cache Process objects across reconciliations.
                        # Reopen and recheck before retaining creation-time identity.
                        fresh = psutil.Process(candidate.pid)
                        if fresh.cmdline() == arguments:
                            process.stop_tree(fresh, self.settings.run_termination_grace_seconds)
                except psutil.NoSuchProcess:
                    continue
                except psutil.AccessDenied:
                    raise ExecutionFailure("ownership_uncertain", "recovery") from None
            failure = {
                "code": "execution_interrupted",
                "stage": "recovery",
                "message": "Application execution was interrupted; this attempt will not resume.",
            }
            try:
                for artifact in run.artifacts.values():
                    verify(self.settings.home, artifact)
            except (OSError, ValueError):
                failure = {
                    "code": "package_corrupt",
                    "stage": "recovery",
                    "message": "Interrupted execution has missing or corrupt frozen evidence.",
                }
            diagnostics = {}
            if directory.is_dir():
                recovery = (
                    strict_json(bounded_read(journal, 1024 * 1024)) if journal.exists() else {}
                )
                recovery["recovery"] = {"finished_at": utc_now(), "failure": failure}
                write_evidence(journal, recovery)
                for name in ("execution.json", "stdout.log", "stderr.log"):
                    path = directory / name
                    if path.exists():
                        diagnostics[name] = reference(
                            self.settings.home, path, max(self.settings.run_log_bytes, 1024 * 1024)
                        )
            self.finish(run.id, failure=failure, artifacts=diagnostics)
        # Orphans are never launched. Rename only validated owned UUID directories;
        # quarantine preserves diagnostic evidence and does not implement garbage collection.
        projects = safe_path(self.settings.home, "projects")
        if projects.exists():
            for project in projects.iterdir():
                try:
                    UUID(project.name)
                except ValueError:
                    continue
                runs = safe_path(self.settings.home, f"projects/{project.name}/runs")
                if not runs.exists():
                    continue
                for directory in runs.iterdir():
                    try:
                        UUID(directory.name)
                    except ValueError:
                        continue
                    if directory.name not in known:
                        safe_path(
                            self.settings.home, directory.relative_to(self.settings.home).as_posix()
                        )
                        quarantine = safe_path(self.settings.home, f".run-orphans/{uuid4()}")
                        quarantine.parent.mkdir(exist_ok=True)
                        directory.rename(quarantine)
