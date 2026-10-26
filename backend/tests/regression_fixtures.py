"""Synthetic source/configuration shared by controlled regression compiler tests."""

import hashlib
from types import SimpleNamespace

import pandas as pd
from pandas.api.types import is_numeric_dtype

from mlstudio.codegen.csv_runtime import parse_csv_bytes
from mlstudio.pipeline_schemas import RegressionPipelineIR
from mlstudio.services.source import describe_columns


def prepared(model="linear_regression", *, mixed=False, data=None, fraction=0.2):
    if data is None:
        header = "x,city,y" if mixed else "x,y"
        rows = [f"{i},c{i},{2 * i + 1}" if mixed else f"{i},{2 * i + 1}" for i in range(20)]
        data = ("\ufeff" + header + "\r\n" + "\r\n".join(rows) + "\r\n").encode()
    frame = parse_csv_bytes(data)
    columns = describe_columns(frame)
    for column in columns:
        if column["name"] != "y" and is_numeric_dtype(frame[column["name"]].dtype):
            column["semantic_override"] = "continuous"
    dataset = SimpleNamespace(
        id="22222222-2222-4222-8222-222222222222",
        fingerprint="sha256:" + hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        columns=columns,
        pandas_version=pd.__version__,
        parsing_version="csv-utf8-v1",
    )
    features = {
        name: {
            "included": True,
            "operations": (
                [{"type": "impute", "strategy": "mean"}, {"type": "scale", "method": "standard"}]
                if is_numeric_dtype(frame[name].dtype)
                else [{"type": "encode", "method": "one_hot"}]
            ),
        }
        for name in frame
        if name != "y"
    }
    ir = RegressionPipelineIR.model_validate(
        {
            "ir_version": "0.2",
            "task": "regression",
            "dataset": {"dataset_id": dataset.id, "fingerprint": dataset.fingerprint},
            "target": {"column": "y"},
            "features": features,
            "model": {"type": model},
            "split": {"test_size": fraction, "random_seed": 42},
        }
    )
    return ir, dataset, frame, data


def plan_for(model="linear_regression", **kwargs):
    from mlstudio.codegen.dispatch import resolve_for_version

    ir, dataset, frame, data = prepared(model, **kwargs)
    plan, issues = resolve_for_version(ir, dataset, "y", frame)
    assert plan is not None, issues
    return plan, frame, data
