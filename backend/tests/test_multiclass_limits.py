"""One combined readiness/legacy boundary regression case (six new tests total)."""

import pandas as pd
import pytest
from test_multiclass import ready_multiclass
from test_projects_datasets import configure, upload

from mlstudio.pipeline_schemas import load_ir
from mlstudio.services.source import DomainError
from mlstudio.services.task_policies import validate_target_for_task
from mlstudio.services.train_validation import train_issues


def test_multiclass_readiness_bounds_and_binary_lossless_labels(client):
    for values in [["a" * 1025, "b", "c"], [2**100, 2**100 + 1, 2**100 + 2]]:
        with pytest.raises(DomainError):
            validate_target_for_task(
                pd.DataFrame({"y": values}),
                "y",
                "multiclass_classification",
                semantic_type="categorical",
            )
    _, state, _ = ready_multiclass(client)
    issues = train_issues(
        load_ir(state["ir"], "multiclass_classification"), pd.Series(["a", "b", "c"] * 133335)
    )
    assert any(i.code == "multiclass_evaluation_limit" for i in issues)
    project = client.post(
        "/api/v1/projects",
        json={"name": "Legacy integers", "problem_statement": "Preserve typed values"},
    ).json()
    assert (
        upload(client, project, b"x,y\n1,9007199254740993\n2,9007199254740995\n").status_code == 201
    )
    result = configure(client, project, target_column="y")
    assert result.status_code == 200, result.text
    assert result.json()["target_classes"] == [
        {"value_type": "integer", "value": "9007199254740993"},
        {"value_type": "integer", "value": "9007199254740995"},
    ]
