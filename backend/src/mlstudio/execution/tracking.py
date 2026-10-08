"""Local, explicit MLflow synchronization. Never authoritative for execution."""

import os
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

from sqlalchemy import select
from sqlalchemy.engine import URL

from mlstudio.execution.artifacts import bounded_read, canonical, safe_path, strict_json, verify
from mlstudio.execution.process import WorkspaceLease
from mlstudio.models import Run, utc_now

_lock = threading.Lock()


def local_artifact_location(home, uri):
    """Reject redirected experiments/runs before any MLflow artifact write."""
    parsed = urlparse(uri)
    if parsed.scheme != "file" or parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("Tracking artifacts must remain local")
    path = Path(url2pathname(parsed.path))
    root = safe_path(home, "mlflow/artifacts")
    path.relative_to(root)
    safe_path(home, path.relative_to(home).as_posix())


def client_for(settings):
    # Client arguments override inherited tracking/registry URIs. No fluent API,
    # autologging, model flavors, tracing, input examples, or remote server.
    os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
    os.environ["MLFLOW_DISABLE_TELEMETRY"] = "true"
    os.environ["MLFLOW_ENABLE_WORKSPACES"] = "false"
    from mlflow.tracking import MlflowClient

    root = safe_path(settings.home, "mlflow")
    root.mkdir(exist_ok=True)
    artifact_root = safe_path(settings.home, "mlflow/artifacts")
    artifact_root.mkdir(exist_ok=True)
    # MLflow's SQL store also initializes a default experiment. Keep even that
    # default inside this workspace (rather than its default ./mlruns).
    os.environ["_MLFLOW_SERVER_ARTIFACT_ROOT"] = artifact_root.as_uri()
    database = safe_path(settings.home, "mlflow/mlflow.db")
    uri = URL.create("sqlite", database=str(database)).render_as_string(hide_password=False)
    return MlflowClient(tracking_uri=uri, registry_uri=uri)


def update(sessions, run_id, **values):
    with sessions() as session:
        run = session.get(Run, run_id)
        if run is None:
            return False  # Explicit Project deletion won the race.
        for name, value in values.items():
            setattr(run, name, value)
        run.tracking_updated_at = utc_now()
        session.commit()
        return True


def synchronize(settings, sessions, run_id):
    """One bounded local synchronization attempt. Failures never escape into execution."""
    lease = None
    acquired = _lock.acquire(timeout=5)
    try:
        if not acquired:
            raise RuntimeError("Tracking is occupied")
        root = safe_path(settings.home, "mlflow")
        root.mkdir(exist_ok=True)
        lease = WorkspaceLease(root)
        with sessions() as session:
            run = session.get(Run, run_id)
            if (
                run is None
                or run.state not in ("SUCCEEDED", "FAILED")
                or run.tracking_status == "SYNCHRONIZED"
            ):
                return
            session.expunge(run)
        client = client_for(settings)
        artifact_root = safe_path(settings.home, f"mlflow/artifacts/{run.project_id}")
        artifact_root.mkdir(parents=True, exist_ok=True)
        experiment = client.get_experiment_by_name(f"mlstudio-{run.project_id}")
        if experiment:
            local_artifact_location(settings.home, experiment.artifact_location)
        experiment_id = (
            experiment.experiment_id
            if experiment
            else client.create_experiment(
                f"mlstudio-{run.project_id}",
                artifact_location=artifact_root.as_uri(),
                tags={"mlstudio.project_id": run.project_id},
            )
        )
        tags = {
            "mlstudio.run_id": run.id,
            "mlstudio.project_id": run.project_id,
            "mlstudio.dataset_id": run.dataset_id,
            "mlstudio.dataset_fingerprint": run.summary["dataset_fingerprint"],
            "mlstudio.sequence": str(run.sequence),
            "mlstudio.state": run.state,
            "mlstudio.source_sha256": run.source_sha256,
            "mlstudio.plan_sha256": run.plan_sha256,
            "mlstudio.generator": run.manifest["provenance"]["generator"],
            "mlstudio.executor": run.manifest["provenance"]["executor"],
        }
        if run.failure:
            tags["mlstudio.failure_code"] = run.failure["code"]
            tags["mlstudio.failure_stage"] = run.failure["stage"]
        external_id = run.mlflow_run_id
        if external_id:
            external = client.get_run(external_id)
            if (
                external.data.tags.get("mlstudio.run_id") != run.id
                or external.info.experiment_id != experiment_id
            ):
                raise ValueError("Tracking association mismatch")
        else:
            matches = client.search_runs(
                [experiment_id], filter_string=f"tags.`mlstudio.run_id` = '{run.id}'", max_results=2
            )
            if len(matches) > 1:
                raise ValueError("Ambiguous tracking association")
            external_id = (
                matches[0].info.run_id
                if matches
                else client.create_run(
                    experiment_id,
                    tags=tags,
                    start_time=int(
                        datetime.fromisoformat(run.started_at or run.created_at).timestamp() * 1000
                    ),
                    run_name=f"Run {run.sequence:03d}",
                ).info.run_id
            )
            if not update(sessions, run.id, mlflow_run_id=external_id):
                return
        local_artifact_location(settings.home, client.get_run(external_id).info.artifact_uri)
        for key, value in tags.items():
            client.set_tag(external_id, key, value, synchronous=True)
        params = {
            "model": run.summary["model"]["name"],
            **{
                f"model.{k}": canonical(v).decode()
                for k, v in run.summary["model"]["parameters"].items()
            },
            **{f"split.{k}": canonical(v).decode() for k, v in run.summary["split"].items()},
            "target": run.summary["target"]["column"],
            "positive_class": canonical(run.summary["target"]["positive_class"]).decode(),
        }
        plan_ref = run.artifacts["execution_plan.json"]
        plan = strict_json(bounded_read(verify(settings.home, plan_ref), plan_ref["size_bytes"]))
        params["preprocessing"] = canonical(
            [
                {"name": feature["name"], "operations": feature["operations"]}
                for feature in plan["features"]
            ]
        ).decode()
        # MLflow's parameter-value limit is finite; the full plan is always an artifact.
        if len(params["preprocessing"]) > 500:
            params["preprocessing"] = f"{len(plan['features'])} features; see execution_plan.json"
        for key, value in params.items():
            client.log_param(external_id, key, value, synchronous=True)
        if run.state == "SUCCEEDED":
            for key, value in run.result["metrics"].items():
                if value is not None:
                    client.log_metric(
                        external_id,
                        key,
                        value,
                        timestamp=int(datetime.fromisoformat(run.finished_at).timestamp() * 1000),
                        step=0,
                        synchronous=True,
                    )
        names = ["pipeline_ir.json", "execution_plan.json", "package.json", "generated_run.py"]
        if run.state == "SUCCEEDED":
            names.append("result.json")
        for name in names:
            client.log_artifact(external_id, str(verify(settings.home, run.artifacts[name])))
        if run.state == "SUCCEEDED":
            verify(settings.home, run.artifacts["model.joblib"])
            client.log_dict(
                external_id,
                {"run_id": run.id, "kind": "complete_pipeline", **run.artifacts["model.joblib"]},
                "model_reference.json",
            )
        client.set_terminated(
            external_id,
            status="FINISHED" if run.state == "SUCCEEDED" else "FAILED",
            end_time=int(datetime.fromisoformat(run.finished_at).timestamp() * 1000),
        )
        update(sessions, run.id, tracking_status="SYNCHRONIZED", tracking_error=None)
    except Exception:
        try:
            update(
                sessions,
                run_id,
                tracking_status="FAILED",
                tracking_error=(
                    "Local MLflow synchronization failed. Execution history is unchanged; "
                    "restart to reconcile tracking."
                ),
            )
        except Exception:
            pass  # A DB outage cannot rewrite the independently committed outcome.
    finally:
        if lease:
            lease.close()
        if acquired:
            _lock.release()


def reconcile(settings, sessions):
    with sessions() as session:
        ids = list(
            session.scalars(
                select(Run.id).where(
                    Run.state.in_(("SUCCEEDED", "FAILED")), Run.tracking_status != "SYNCHRONIZED"
                )
            )
        )
    for run_id in ids:
        synchronize(settings, sessions, run_id)
