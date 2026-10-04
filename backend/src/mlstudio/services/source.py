"""Explicit csv-utf8-v1 parsing and deterministic source observations."""

import math
import re
from pathlib import Path

import pandas as pd
from pandas.api.types import is_bool_dtype, is_integer_dtype, is_numeric_dtype

from mlstudio.codegen.csv_runtime import parse_csv_bytes

PREVIEW_LIMIT = 20


class DomainError(Exception):
    def __init__(self, message: str, status_code: int = 422):
        self.message = message
        self.status_code = status_code


def parse_source(path: Path) -> pd.DataFrame:
    try:
        return parse_csv_bytes(path.read_bytes())
    except ValueError as error:
        raise DomainError(str(error)) from None


def json_scalar(value):
    """Convert pandas/numpy scalars explicitly; JSON never receives NaN/Infinity."""
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, int) and not isinstance(value, bool) and abs(value) > 2**53 - 1:
        return {"value_type": "integer", "value": str(value)}
    if isinstance(value, float) and not math.isfinite(value):
        raise DomainError("Non-finite numeric values are not supported in CSV datasets.")
    if isinstance(value, (str, bool, int, float)):
        return value
    raise DomainError("CSV contains an unsupported scalar representation.")


def infer_semantic(series: pd.Series) -> str:
    """Ordered conservative rules; uniqueness by itself never implies identity."""
    observed = series.dropna()
    unique = observed.nunique()
    if unique == 0:
        return "unknown"
    if unique == 2:
        return "binary"
    # Split CamelCase and punctuation; never match the substring in paid/width/middle.
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(series.name)).lower()
    tokens = re.findall(r"[a-z0-9]+", name)
    id_hint = bool(set(tokens) & {"id", "uuid", "guid", "identifier", "key"})
    integer_like = is_integer_dtype(series.dtype) or (
        is_numeric_dtype(series.dtype)
        and not is_bool_dtype(series.dtype)
        and observed.map(lambda v: math.isfinite(v) and v == int(v)).all()
    )
    strings = not is_numeric_dtype(series.dtype) and not is_bool_dtype(series.dtype)
    if unique >= 3 and unique / len(observed) >= 0.95:
        values = observed.astype(str) if strings else None
        uuid_like = (
            values is not None
            and values.str.fullmatch(
                r"(\{)?[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}(?(1)\})"
            ).all()
        )
        opaque = values is not None and values.str.fullmatch(r"[A-Za-z0-9_-]+").all()
        date_like = values is not None and values.str.match(r"\d{4}-\d{2}-\d{2}").all()
        if uuid_like or (id_hint and (integer_like or (opaque and not date_like))):
            return "identifier"
    if is_numeric_dtype(series.dtype) and not is_bool_dtype(series.dtype):
        return "continuous" if unique > 1 else "unknown"
    if strings:
        values = observed.astype(str)
        # Only unambiguous ISO-looking strings; never parse numeric timestamps.
        if values.map(
            lambda value: bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[T ].+)?", value))
        ).all():
            if pd.to_datetime(values, format="ISO8601", errors="coerce").notna().all():
                return "datetime"
        if values.str.len().gt(80).any() or values.str.split().str.len().ge(8).any():
            return "text"
        if unique <= 20 or unique / len(observed) <= 0.2:
            return "categorical"
        return "text"
    return "unknown"


def describe_columns(frame: pd.DataFrame) -> list[dict]:
    columns = []
    for order, name in enumerate(frame.columns):
        series = frame[name]
        # Reject infinities anywhere, not merely in the preview or selected target.
        if is_numeric_dtype(series.dtype):
            if series.isin([float("inf"), float("-inf")]).any():
                raise DomainError("Non-finite numeric values are not supported in CSV datasets.")
        columns.append(
            {
                "name": name,
                "source_order": order,
                "physical_dtype": str(series.dtype),
                "missing_count": int(series.isna().sum()),
                "unique_count": int(series.nunique()),
                "inferred_semantic_type": infer_semantic(series),
                "semantic_override": None,
                "inference_version": "semantic-v2",
            }
        )
    return columns


def target_classes(frame: pd.DataFrame, name: str) -> list:
    if name not in frame.columns:
        raise DomainError("Target must belong to the active Dataset.")
    values = frame[name].dropna().unique()
    if len(values) != 2:
        raise DomainError(
            "Binary targets need exactly 2 distinct non-missing classes; "
            f"this column has {len(values)}."
        )
    return [json_scalar(value) for value in values]
