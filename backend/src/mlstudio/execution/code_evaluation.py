"""Freeze bounded Code reporting after process cleanup; read historical bytes only."""

from mlstudio.code_runtime import MAX_BYTES, MULTICLASS_SCHEMA, SCHEMA, validate_report
from mlstudio.execution.artifacts import (
    bounded_read,
    reference,
    safe_path,
    strict_json,
    verify,
    write_new,
)


def finalize(settings, run):
    if run.status != "COMPLETED":
        return {"status": "execution_incomplete"}
    root = safe_path(settings.home, run.artifact_directory)
    try:
        data = bounded_read(root / "workspace" / "code-evaluation.json", MAX_BYTES)
    except FileNotFoundError:
        return {"status": "not_reported"}
    except (OSError, ValueError):
        return {"status": "invalid"}
    try:
        report = strict_json(data)
        validate_report(report, run.configuration.get("reporting", {}).get("task"))
        # Freeze the exact reported bytes, not recomputed metrics or a parsed rewrite.
        path = root / "evaluation.json"
        write_new(path, data)
        return {
            "status": "available",
            "schema_version": report["schema_version"],
            "artifact": reference(settings.home, path, MAX_BYTES),
        }
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        OverflowError,
        RecursionError,
        AttributeError,
    ):
        return {"status": "invalid"}


def evaluation(settings, run):
    if run.status in ("PENDING", "RUNNING"):
        return {"status": "pending", "report": None}
    if run.status != "COMPLETED":
        return {"status": "execution_incomplete", "report": None}
    evidence = run.logs.get("evaluation", {"status": "not_reported"})
    status = evidence["status"]
    if status != "available":
        return {"status": status, "report": None}
    try:
        path = verify(settings.home, evidence["artifact"])
        expected = f"{run.artifact_directory}/evaluation.json"
        if evidence["artifact"]["path"] != expected or evidence["schema_version"] not in (
            SCHEMA,
            MULTICLASS_SCHEMA,
        ):
            raise ValueError("Unexpected reporting artifact.")
        from mlstudio.execution.code_runs import response

        if response(settings, run, include_source=False).source_integrity != "verified":
            raise ValueError("Source integrity failed.")
        report = strict_json(bounded_read(path, MAX_BYTES))
        if report["schema_version"] != evidence["schema_version"]:
            raise ValueError("Reporting schema changed.")
        validate_report(report, run.configuration.get("reporting", {}).get("task"))
        return {"status": "available", "report": report}
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        OverflowError,
        RecursionError,
        AttributeError,
    ):
        return {"status": "unavailable_or_corrupt", "report": None}
