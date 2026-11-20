"""Portable training-fitted selective imputation over immutable input snapshots."""

import copy
import math
import re

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

from mlstudio.derived_runtime_v1 import derived_transform, derived_validate


class ImputationValidationError(ValueError):
    """Sanitized configuration or data error suitable for generated execution."""


def imputation_dict(config):
    return config.model_dump(mode="json") if hasattr(config, "model_dump") else config


def imputation_bounds(config):
    """Bound raw trees before recursive parsing, copying or expression admission."""
    config = imputation_dict(config)
    columns = config.get("columns", {})
    if not isinstance(columns, dict) or len(columns) > 64:
        raise ImputationValidationError("Imputation columns exceed bounded limit.")
    total = 0
    for column in columns.values():
        column = imputation_dict(column)
        if not isinstance(column, dict):
            raise ImputationValidationError("Invalid imputation column configuration.")
        rules = column.get("rules", [])
        if not isinstance(rules, list) or not 1 <= len(rules) <= 16:
            raise ImputationValidationError("Imputation rules exceed bounded limit.")
        for rule in rules:
            rule = imputation_dict(rule)
            if not isinstance(rule, dict):
                raise ImputationValidationError("Invalid imputation rule configuration.")
            condition = rule.get("condition")
            stack = [] if condition is None else [(imputation_dict(condition), 0)]
            nodes = 0
            while stack:
                node, depth = stack.pop()
                nodes += 1
                total += 1
                if total > 4096:
                    raise ImputationValidationError(
                        "Imputation total predicate node limit exceeded."
                    )
                if not isinstance(node, dict) or depth > 8 or nodes > 256:
                    raise ImputationValidationError(
                        "Imputation predicate exceeds bounded tree limits."
                    )
                args = node.get("arguments", [])
                if not isinstance(args, list) or len(args) > 16:
                    raise ImputationValidationError("Imputation predicate argument limit exceeded.")
                stack.extend((arg, depth + 1) for arg in args)


def imputation_predicate(condition, input_types):
    """Normalize physical pre-imputation references into the existing derived AST."""
    stack, nodes = [(condition, 0)], 0
    while stack:
        node, depth = stack.pop()
        nodes += 1
        if not isinstance(node, dict) or depth > 8 or nodes > 256:
            raise ImputationValidationError("Imputation predicate exceeds bounded tree limits.")
        args = node.get("arguments", [])
        if not isinstance(args, list) or len(args) > 16:
            raise ImputationValidationError("Imputation predicate exceeds bounded argument limit.")
        stack.extend((arg, depth + 1) for arg in args)
    expression = copy.deepcopy(condition)
    stack = [expression]
    while stack:
        node = stack.pop()
        if node.get("kind") == "reference":
            node["kind"] = "column"
        stack.extend(node.get("arguments", []))
    name = "ImputationPredicate"
    while name in input_types:
        name += "X"
    return {
        "version": "derived-v1",
        "input_types": input_types,
        "features": [{"name": name, "expression": expression}],
    }, name


def imputation_validate(config, input_types, target=None):
    config = imputation_dict(config)
    imputation_bounds(config)
    columns = config.get("columns", {})
    if config.get("version", "imputation-v1") != "imputation-v1":
        raise ImputationValidationError("Unsupported imputation configuration version.")
    if not isinstance(columns, dict) or len(columns) > 64:
        raise ImputationValidationError("Imputation columns exceed bounded limit.")
    indicators = set()
    for name, column in columns.items():
        if not isinstance(name, str) or not name or len(name) > 200 or name == target:
            raise ImputationValidationError("Invalid imputation column or supervised target.")
        kind = input_types.get(name)
        if kind not in {"numeric", "boolean", "string"}:
            raise ImputationValidationError("Imputation column is absent or unsupported.")
        indicator = column.get("indicator")
        if indicator is not None:
            if (
                not isinstance(indicator, str)
                or len(indicator) > 200
                or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", indicator)
                or indicator in input_types
                or indicator in indicators
                or indicator == target
            ):
                raise ImputationValidationError("Imputation indicator name is invalid or collides.")
            indicators.add(indicator)
        rules = column.get("rules", [])
        if not isinstance(rules, list) or not 1 <= len(rules) <= 16:
            raise ImputationValidationError("Imputation rules exceed bounded limit.")
        for rule in [*rules, column.get("fallback", {"strategy": "leave_missing"})]:
            strategy = rule.get("strategy")
            if strategy not in {"constant", "mean", "median", "most_frequent", "leave_missing"}:
                raise ImputationValidationError("Unsupported imputation strategy.")
            if strategy in {"mean", "median"} and kind != "numeric":
                raise ImputationValidationError("Mean and median require a numeric column.")
            if strategy == "constant":
                value = rule.get("value")
                valid = (
                    (kind == "numeric" and type(value) in (int, float))
                    or (kind == "boolean" and type(value) is bool)
                    or (kind == "string" and type(value) is str)
                )
                if not valid or (type(value) is str and len(value) > 1000):
                    raise ImputationValidationError("Imputation constant has incompatible type.")
                if type(value) in (int, float):
                    if (type(value) is int and abs(value) > 2**53 - 1) or not math.isfinite(value):
                        raise ImputationValidationError(
                            "Imputation constant must be finite and safe."
                        )
            group_by = rule.get("group_by", [])
            if not isinstance(group_by, list) or len(group_by) > 4:
                raise ImputationValidationError("Imputation grouping exceeds bounded limit.")
            if len(set(group_by)) != len(group_by):
                raise ImputationValidationError("Duplicate imputation grouping columns.")
            for group in group_by:
                if group in {name, target} or input_types.get(group) not in {
                    "numeric",
                    "boolean",
                    "string",
                }:
                    raise ImputationValidationError("Imputation grouping column is invalid.")
            condition = rule.get("condition")
            if condition is not None:
                predicate, output = imputation_predicate(condition, input_types)
                try:
                    _, inferred = derived_validate(predicate, input_types, target)
                except (ValueError, TypeError, KeyError) as exc:
                    raise ImputationValidationError(
                        "Invalid imputation predicate or input type."
                    ) from exc
                if inferred[output] != "boolean":
                    raise ImputationValidationError(
                        "Imputation condition must produce boolean values."
                    )


def validate_imputation(config, input_types, target=None):
    """Public portable admission interface shared by services and schema callers."""
    return imputation_validate(config, input_types, target)


def imputation_types(frame, declared=None):
    result = dict(declared or {})
    for name in frame:
        if name in result:
            continue
        series = frame[name]
        observed = series.dropna()
        if pd.api.types.is_bool_dtype(series.dtype) or (
            len(observed) and observed.map(lambda v: isinstance(v, (bool, np.bool_))).all()
        ):
            result[name] = "boolean"
        elif pd.api.types.is_numeric_dtype(series.dtype) or (
            len(observed)
            and observed.map(
                lambda v: (
                    isinstance(v, (int, float, np.integer, np.floating))
                    and not isinstance(v, (bool, np.bool_))
                )
            ).all()
        ):
            result[name] = "numeric"
        else:
            result[name] = "string"
    return result


def imputation_inputs(frame, config, input_types):
    """Validate only required inputs; unconfigured columns pass through unchanged."""
    if not isinstance(frame, pd.DataFrame) or not frame.columns.is_unique:
        raise ImputationValidationError("Imputation requires uniquely named dataframe columns.")
    required = set(config["columns"])
    for column in config["columns"].values():
        for rule in column["rules"]:
            required.update(rule.get("group_by", []))
            stack = [rule.get("condition")]
            while stack:
                node = stack.pop()
                if not isinstance(node, dict):
                    continue
                if node.get("kind") in {"column", "reference"}:
                    required.add(node.get("name"))
                stack.extend(node.get("arguments", []))
    if not (required | set(config.get("input_dtypes", {}))).issubset(frame.columns):
        raise ImputationValidationError("A required pre-imputation input column is absent.")
    result = frame.copy()
    for name in required:
        kind = input_types.get(name)
        observed = frame[name].dropna()
        if kind == "numeric":
            valid = observed.map(
                lambda v: (
                    isinstance(v, (int, float, np.integer, np.floating))
                    and not isinstance(v, (bool, np.bool_))
                )
            ).all()
            if not valid:
                raise ImputationValidationError("Imputation numeric input has incompatible values.")
            if observed.map(
                lambda v: isinstance(v, (int, np.integer)) and abs(int(v)) > 2**53 - 1
            ).any():
                raise ImputationValidationError("Imputation integer input exceeds safe range.")
            result[name] = frame[name].astype(float)
            if not np.isfinite(result[name].dropna()).all():
                raise ImputationValidationError("Imputation numeric input must be finite.")
        elif kind == "boolean":
            # Derived boolean outputs are physical float 0/1; declared type stays boolean.
            valid = observed.map(
                lambda v: (
                    isinstance(v, (bool, np.bool_))
                    or (isinstance(v, (int, float, np.integer, np.floating)) and v in (0, 1))
                )
            ).all()
            if not valid:
                raise ImputationValidationError("Imputation boolean input has incompatible values.")
            result[name] = frame[name].astype("boolean")
        elif kind == "string":
            if not observed.map(lambda v: isinstance(v, str)).all():
                raise ImputationValidationError("Imputation string input has incompatible values.")
            result[name] = frame[name].astype(object).where(frame[name].notna(), np.nan)
        else:
            raise ImputationValidationError("Unsupported imputation input type.")
    return result


def imputation_matches(frame, condition, input_types):
    if condition is None:
        return pd.Series(True, index=frame.index)
    predicate, name = imputation_predicate(condition, input_types)
    try:
        result = derived_transform(frame, predicate)[0][name]
    except (ValueError, TypeError, KeyError) as exc:
        raise ImputationValidationError(
            "Imputation predicate cannot evaluate the supplied inputs."
        ) from exc
    return result.eq(1).fillna(False).astype(bool)


def imputation_keys(frame, group_by, input_types):
    """Typed tuple keys; missing keys never match a fitted group."""
    return [
        None
        if any(pd.isna(v) for v in values)
        else tuple(
            (input_types[name], bool(value) if input_types[name] == "boolean" else value)
            for name, value in zip(group_by, values, strict=True)
        )
        for values in frame[group_by].itertuples(index=False, name=None)
    ]


def imputation_statistic(series, strategy):
    observed = series.dropna()
    if observed.empty:
        return None
    if strategy in {"mean", "median"}:
        value = float(observed.mean() if strategy == "mean" else observed.median())
        if not math.isfinite(value):
            raise ImputationValidationError(
                "Imputation statistic is non-finite; use constant fallback."
            )
        return value
    counts = observed.value_counts(sort=False)
    return min(counts[counts == counts.max()].index)


def imputation_diagnostics(frame, config):
    """No fitting: independent predicate matches among originally missing cells."""
    config = imputation_dict(config)
    types = imputation_types(frame, config.get("input_types"))
    imputation_validate(config, types)
    original = imputation_inputs(frame, config, types)
    return {
        name: {
            "missing_count": int(original[name].isna().sum()),
            "rule_matches": [
                int(
                    (
                        original[name].isna()
                        & imputation_matches(original, rule.get("condition"), types)
                    ).sum()
                )
                for rule in column["rules"]
            ],
            "indicator_values": original[name].isna().astype(float).head(20).tolist()
            if column.get("indicator")
            else [],
        }
        for name, column in config["columns"].items()
    }


class ImputationFeatures(TransformerMixin, BaseEstimator):
    """Fit donors once; evaluate all conditions and groups on original input values."""

    def __init__(self, config):
        self.config = config

    def fit(self, X, y=None):
        config = imputation_dict(self.config)
        self.input_types_ = imputation_types(X, config.get("input_types"))
        imputation_validate(config, self.input_types_)
        self.config_ = copy.deepcopy(config)
        original = imputation_inputs(X, self.config_, self.input_types_)
        self.feature_names_in_ = np.asarray(X.columns, dtype=object)
        self.n_features_in_ = len(X.columns)
        self.statistics_ = {}
        total_groups = 0
        for name, column in self.config_["columns"].items():
            fallback = column.get("fallback", {"strategy": "leave_missing"})
            if original[name].notna().sum() == 0 and fallback["strategy"] != "constant":
                raise ImputationValidationError(
                    "All-missing training column requires a compatible constant fallback."
                )
            fitted = []
            for rule in [*column["rules"], fallback]:
                strategy, groups = rule["strategy"], rule.get("group_by", [])
                if groups:
                    keys = imputation_keys(original, groups, self.input_types_)
                    donors = pd.DataFrame(
                        {
                            "key": pd.Series(keys, dtype=object),
                            "value": original[name].reset_index(drop=True),
                        }
                    ).groupby("key", sort=False, dropna=True)["value"]
                    group_count = donors.ngroups
                    if group_count > 10000:
                        raise ImputationValidationError(
                            "Imputation group cardinality limit exceeded."
                        )
                    total_groups += group_count
                    if total_groups > 50000:
                        raise ImputationValidationError(
                            "Total imputation group cardinality limit exceeded."
                        )
                    if strategy == "constant":
                        mapping = dict.fromkeys(donors.size().index, rule.get("value"))
                    else:
                        if strategy in {"mean", "median"}:
                            statistics = getattr(donors, strategy)()
                            if not np.isfinite(statistics.dropna()).all():
                                raise ImputationValidationError(
                                    "Imputation statistic is non-finite; use constant fallback."
                                )
                        else:
                            statistics = donors.agg(
                                lambda values, strategy=strategy: imputation_statistic(
                                    values, strategy
                                )
                            )
                        mapping = {
                            key: None if pd.isna(value) else value
                            for key, value in statistics.items()
                        }
                    fitted.append(mapping)
                else:
                    fitted.append(
                        rule.get("value")
                        if strategy == "constant"
                        else (
                            None
                            if strategy == "leave_missing"
                            else imputation_statistic(original[name], strategy)
                        )
                    )
            if fallback["strategy"] in {"mean", "median", "most_frequent"} and fitted[-1] is None:
                raise ImputationValidationError(
                    "Fallback training statistic is unavailable; use a constant."
                )
            self.statistics_[name] = fitted
        return self

    def transform(self, X):
        if not hasattr(self, "statistics_"):
            raise ImputationValidationError("Fit advanced imputation before transformation.")
        original = imputation_inputs(X, self.config_, self.input_types_)
        result = X.copy()
        for name, column in self.config_["columns"].items():
            value = original[name].copy()
            for rule, fitted in zip(
                [*column["rules"], column.get("fallback", {"strategy": "leave_missing"})],
                self.statistics_[name],
                strict=True,
            ):
                missing = value.isna() & imputation_matches(
                    original, rule.get("condition"), self.input_types_
                )
                groups = rule.get("group_by", [])
                replacement = (
                    pd.Series(
                        [
                            fitted.get(key) if key is not None else None
                            for key in imputation_keys(original, groups, self.input_types_)
                        ],
                        index=X.index,
                        dtype=object,
                    )
                    if groups
                    else fitted
                )
                if replacement is not None:
                    value = value.where(~missing, replacement)
            if value.isna().any():
                raise ImputationValidationError(
                    "Advanced imputation leaves remaining missing values; configure a usable "
                    "fallback or another rule before training or prediction."
                )
            result[name] = (
                value.astype(float)
                if self.input_types_[name] in {"numeric", "boolean"}
                else value.astype(object)
            )
            if column.get("indicator"):
                result[column["indicator"]] = original[name].isna().astype(float)
        return result

    def get_feature_names_out(self, input_features=None):
        names = self.feature_names_in_ if input_features is None else input_features
        return np.asarray(
            [
                *names,
                *[
                    column["indicator"]
                    for column in self.config_["columns"].values()
                    if column.get("indicator")
                ],
            ],
            dtype=object,
        )


def register_imputation_transformer():
    """Register the fixed class for trusted standalone generated-model pickles."""
    import sys
    import types

    name = "mlstudio.imputation_runtime_v1"
    if "mlstudio" not in sys.modules:
        parent = types.ModuleType("mlstudio")
        parent.__path__ = []
        sys.modules["mlstudio"] = parent
    if name not in sys.modules:
        module = types.ModuleType(name)
        # Class methods keep their function globals, including embedded helper functions.
        module.__dict__.update(
            {
                key: value
                for key, value in globals().items()
                if key.startswith("imputation_")
                or key in {"ImputationFeatures", "ImputationValidationError"}
            }
        )
        sys.modules[name] = module
        ImputationFeatures.__module__ = name
    return sys.modules[name].ImputationFeatures
