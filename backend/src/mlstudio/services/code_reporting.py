"""Reviewed proposals for known generated drafts; never rewrite arbitrary Python."""

import ast
from difflib import unified_diff

from mlstudio.code_draft_schemas import DraftSave
from mlstudio.code_runtime import code_mode_source, reporting_block
from mlstudio.services.code_drafts import writable


def proposal(session, project, draft_id, body):
    draft = writable(session, project.id, draft_id, body.revision)
    task = "regression" if draft.origin_ir.get("task") == "regression" else "binary_classification"
    example = (
        "from mlstudio_runtime import report_regression\n"
        "report_regression(y_true=your_test_targets, y_pred=your_predictions)"
        if task == "regression"
        else "from mlstudio_runtime import report_classification\n"
        "report_classification(y_true=your_test_targets, y_pred=your_predictions,\n"
        "                      labels=[your_negative_class, your_positive_class])"
    )
    result = {
        "status": "manual",
        "revision": draft.revision,
        "proposed_source": None,
        "diff": "",
        "example": example,
        "message": "This script differs from the preserved generated structure. "
        "No automatic change is proposed. Add the example after producing "
        "test predictions, using your own variables and typed class order.",
    }
    try:
        tree = ast.parse(body.source)
        calls = {"report_classification", "report_regression"}
        names = set(calls)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "mlstudio_runtime":
                names.update(
                    alias.asname or alias.name for alias in node.names if alias.name in calls
                )
        if any(
            isinstance(node, ast.Call)
            and (
                isinstance(node.func, ast.Name)
                and node.func.id in names
                or isinstance(node.func, ast.Attribute)
                and node.func.attr in calls
            )
            for node in ast.walk(tree)
        ):
            return {
                **result,
                "status": "present",
                "message": "An evaluation reporting call already exists. "
                "No additional call will be inserted. Check its inputs and logs "
                "if evaluation is unavailable.",
            }
        baseline = draft.baseline_source.replace("\r\n", "\n")
        baseline = baseline.replace(reporting_block(task), "")
        # Conservative allowlist: executable AST must match the immutable baseline.
        # Comments/formatting are preserved byte-for-byte; renames/logic changes
        # get a manual example instead of guessed variable/data-flow rewriting.
        if ast.dump(tree) != ast.dump(ast.parse(baseline)):
            return result
        proposed = code_mode_source(body.source, task)
        ast.parse(proposed)  # Unsupported indentation must not yield a broken proposal.
        DraftSave(revision=body.revision, source=proposed)
    except (SyntaxError, ValueError, TypeError, RecursionError):
        return result
    return {
        **result,
        "status": "ready",
        "proposed_source": proposed,
        "diff": "".join(
            unified_diff(
                body.source.splitlines(keepends=True),
                proposed.splitlines(keepends=True),
                fromfile="current.py",
                tofile="proposed.py",
            )
        ),
        "message": "The executable structure matches the preserved generated baseline. "
        "Review the reporting-only insertion before applying. "
        "Comments and unrelated text are preserved; nothing has been saved yet.",
    }
