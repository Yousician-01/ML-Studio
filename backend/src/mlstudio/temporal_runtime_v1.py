"""Frozen temporal-v1 runtime, also embedded verbatim in generated Python.

Only stateless calculation happens here. Imputation/scaling remain training-only.
All calendar extraction is in UTC. No clock, date inference or arbitrary expression code.
"""

import re

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin


def temporal_parse(series, policy):
    """Return UTC timestamps and aggregate diagnostics, never source values in errors."""
    fmt = policy.get("format", "ISO8601")
    strings = series.map(lambda value: isinstance(value, str))
    values = series.where(strings)
    if fmt == "ISO8601":
        iso = values.map(
            lambda value: (
                isinstance(value, str)
                and bool(
                    re.fullmatch(
                        r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d{1,9})?)?"
                        r"(?:Z|[+-]\d{2}:?\d{2})?)?",
                        value,
                    )
                )
            )
        )
        values = values.where(iso)
    if policy.get("naive", "reject") == "reject" and fmt == "ISO8601":
        aware = values.map(
            lambda value: (
                isinstance(value, str) and bool(re.search(r"(?:Z|[+-]\d{2}:?\d{2})$", value))
            )
        )
        values = values.where(aware)
    elif policy.get("naive", "reject") == "reject" and "%z" not in fmt:
        values = values.where(pd.Series(False, index=values.index))
    parsed = pd.to_datetime(values, format=fmt, errors="coerce", utc=True)
    return parsed, {
        "missing_count": int(series.isna().sum()),
        "invalid_count": int((series.notna() & parsed.isna()).sum()),
        "date_only_count": int(
            series.map(
                lambda value: (
                    isinstance(value, str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))
                )
            ).sum()
        ),
    }


def temporal_literal(value):
    parsed, counts = temporal_parse(pd.Series([value]), {"naive": "utc"})
    if counts["invalid_count"]:
        raise ValueError("Reference datetime must be an explicit ISO8601 date or timestamp.")
    return parsed.iloc[0]


def temporal_transform(frame, config, *, diagnostic=False):
    """A small typed interpreter. Config is validated before preview/code admission."""
    sources, counts = {}, {}
    for name, policy in config["sources"].items():
        if name not in frame:
            raise ValueError("A configured datetime source column is absent.")
        sources[name], counts[name] = temporal_parse(frame[name], policy)
        if counts[name]["invalid_count"] and policy.get("invalid", "reject") == "reject":
            if not diagnostic:
                raise ValueError("Datetime source contains invalid or disallowed timestamps.")
    definitions = {feature["name"]: feature["expression"] for feature in config["features"]}
    cache, metadata, visiting = {}, {}, set()

    def evaluate(expression):
        kind = expression["kind"]
        if kind == "column":
            return sources[expression["name"]], None
        if kind == "literal":
            return pd.Series(temporal_literal(expression["value"]), index=frame.index), None
        if kind == "reference":
            return derived(expression["name"])
        op = expression["operation"]
        args = [evaluate(arg) for arg in expression["arguments"]]
        left = args[0][0]
        if op in {"cyclic_sin", "cyclic_cos"}:
            period, base = {
                "quarter": (4, 1),
                "month": (12, 1),
                "day_of_week": (7, 0),
                "hour": (24, 0),
                "minute": (60, 0),
                "second": (60, 0),
            }[args[0][1]]
            angle = 2 * np.pi * (left - base) / period
            return (np.sin(angle) if op == "cyclic_sin" else np.cos(angle)), op
        if op == "date_diff":
            seconds = (left - args[1][0]).dt.total_seconds()
            unit = expression["parameters"]["unit"]
            return seconds / {"seconds": 1, "minutes": 60, "hours": 3600, "days": 86400}[unit], op
        if op == "calendar_age":
            reference = args[1][0]
            before = reference < left
            start, end = left.where(~before, reference), reference.where(~before, left)
            anniversary_not_reached = (end.dt.month < start.dt.month) | (
                (end.dt.month == start.dt.month) & (end.dt.day < start.dt.day)
            )
            years = end.dt.year - start.dt.year - anniversary_not_reached.astype(float)
            return years.where(~before, -years).where(left.notna() & reference.notna()), op
        if op == "iso_week":
            value = left.dt.isocalendar().week
        elif op == "iso_year":
            value = left.dt.isocalendar().year
        elif op == "is_weekend":
            value = left.dt.dayofweek >= 5
        else:
            attribute = {"day_of_week": "dayofweek", "day_of_year": "dayofyear"}.get(op, op)
            value = getattr(left.dt, attribute)
        return value.astype(float).where(left.notna()), op

    def derived(name):
        if name in cache:
            return cache[name], metadata[name]
        if name in visiting:
            raise ValueError("Cyclic temporal dependencies.")
        visiting.add(name)
        value, component = evaluate(definitions[name])
        cache[name] = value.astype(float)
        metadata[name] = component
        visiting.remove(name)
        return cache[name], component

    result = frame.copy()
    for name in definitions:
        result[name] = derived(name)[0]
    return result, counts


class TemporalFeatures(TransformerMixin, BaseEstimator):
    """Preserve raw source columns; append only explicitly declared outputs."""

    def __init__(self, config):
        self.config = config

    def fit(self, X, y=None):
        self.feature_names_in_ = np.asarray(X.columns, dtype=object)
        self.n_features_in_ = len(X.columns)
        return self

    def transform(self, X):
        return temporal_transform(X, self.config)[0]

    def get_feature_names_out(self, input_features=None):
        names = self.feature_names_in_ if input_features is None else input_features
        return np.asarray([*names, *[f["name"] for f in self.config["features"]]], dtype=object)


def register_temporal_transformer():
    """Standalone source supplies the same versioned pickle class as the package.

    Importing frozen generated source before loading its trusted model also enables
    standalone inference without the ML Studio backend. No config/code is evaluated.
    """
    import sys
    import types

    name = "mlstudio.temporal_runtime_v1"
    if "mlstudio" not in sys.modules:
        parent = types.ModuleType("mlstudio")
        parent.__path__ = []
        sys.modules["mlstudio"] = parent
    if name not in sys.modules:
        module = types.ModuleType(name)
        module.TemporalFeatures = TemporalFeatures
        sys.modules[name] = module
        TemporalFeatures.__module__ = name
    return sys.modules[name].TemporalFeatures
