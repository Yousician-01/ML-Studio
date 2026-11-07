"""Portable, stateless interpreter shared by preview, fitting and frozen Python."""

import math
import re

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin


def derived_bounds(config):
    """Iterative admission check runs before recursive Pydantic/tree processing."""
    features = config.get("features", [])
    if not isinstance(features, (list, tuple)) or len(features) > 128:
        raise ValueError("Derived features exceed bounded feature limit.")
    total = 0
    for feature in features:
        if not isinstance(feature, dict):
            raise ValueError("Invalid derived feature definition.")
        stack, nodes = [(feature.get("expression"), 0)], 0
        while stack:
            expression, depth = stack.pop()
            nodes += 1
            total += 1
            if depth > 8 or nodes > 256 or total > 1024:
                raise ValueError("Derived expressions exceed bounded depth or node limit.")
            if not isinstance(expression, dict):
                raise ValueError("Invalid derived expression.")
            args = expression.get("arguments", [])
            if not isinstance(args, (list, tuple)) or len(args) > 16:
                raise ValueError("Derived arguments exceed bounded limit.")
            stack.extend((arg, depth + 1) for arg in args)


def derived_validate(config, source_types, target=None, temporal_types=None):
    """Infer compact types and stable dependency order without executable expressions."""
    derived_bounds(config)
    if config.get("version", "derived-v1") != "derived-v1":
        raise ValueError("Unsupported derived feature version.")
    temporal_types = temporal_types or {}
    definitions = {}
    for feature in config.get("features", []):
        name = feature.get("name")
        if (
            not isinstance(name, str)
            or len(name) > 200
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name)
        ):
            raise ValueError("Invalid derived output name.")
        if name in definitions:
            raise ValueError("Duplicate derived feature names.")
        if name in source_types or name in temporal_types or name == target:
            raise ValueError("Derived feature names collide with source columns.")
        definitions[name] = feature["expression"]
    order, types, visiting, levels = [], {}, set(), {}
    numeric_binary = {
        "add",
        "subtract",
        "multiply",
        "safe_divide",
        "modulo",
        "power",
        "minimum",
        "maximum",
    }
    numeric_unary = {"abs", "negate", "sqrt", "log", "log1p", "round", "floor", "ceil"}
    comparisons = {
        "equal",
        "not_equal",
        "greater",
        "greater_equal",
        "less",
        "less_equal",
    }

    def compatible(args):
        nonnull = set(args) - {"null"}
        if len(nonnull) > 1:
            raise ValueError("Expression arguments require compatible types.")
        return next(iter(nonnull), "null")

    def infer(expression, dependencies):
        kind = expression.get("kind")
        if kind in {"column", "reference"}:
            name = expression.get("name")
            if not isinstance(name, str) or not name or len(name) > 200 or name == target:
                raise ValueError("Expression cannot reference the target or an invalid input.")
            if kind == "reference" and name in definitions:
                result = visit(name)
                dependencies.append(levels[name])
                return result
            available = source_types if kind == "column" else temporal_types
            result = available.get(name)
            if result not in {"numeric", "boolean", "string"} or (
                kind == "reference" and result == "string"
            ):
                raise ValueError("Unresolved or unsupported expression input reference.")
            return result
        if kind == "literal":
            value = expression.get("value")
            if value is None:
                return "null"
            if type(value) is bool:
                return "boolean"
            if type(value) is str and len(value) <= 1000:
                return "string"
            if type(value) is int and abs(value) > 2**53 - 1:
                raise ValueError(
                    "Exact integer literal is outside supported safe range; "
                    "use a value between -(2**53 - 1) and 2**53 - 1."
                )
            if type(value) in (int, float):
                try:
                    if math.isfinite(value):
                        return "numeric"
                except OverflowError:
                    pass
            raise ValueError("Literal must be a bounded finite JSON primitive.")
        if kind != "call":
            raise ValueError("Unsupported expression kind.")
        op = expression.get("operation")
        arguments = expression.get("arguments", [])
        args = [infer(arg, dependencies) for arg in arguments]
        parameters = expression.get("parameters", {})
        if not isinstance(parameters, dict) or set(parameters) - {"precision"}:
            raise ValueError("Unsupported operation parameters.")
        precision = parameters.get("precision")
        if precision is not None and (
            op != "round" or type(precision) is not int or not -12 <= precision <= 12
        ):
            raise ValueError("Round precision must be an integer between -12 and 12.")
        if op in numeric_binary | numeric_unary:
            if len(args) != (2 if op in numeric_binary else 1) or any(
                a not in {"numeric", "null"} for a in args
            ):
                raise ValueError("Arithmetic requires numeric arguments and the correct arity.")
            return "numeric"
        if op in comparisons:
            if len(args) != 2:
                raise ValueError("Comparison requires two arguments.")
            compatible(args)
            return "boolean"
        if op in {"and", "or", "not"}:
            if len(args) != (1 if op == "not" else 2) or any(
                a not in {"boolean", "null"} for a in args
            ):
                raise ValueError("Boolean logic requires boolean arguments.")
            return "boolean"
        if op in {"is_missing", "is_not_missing"} and len(args) == 1:
            return "boolean"
        if op == "if" and len(args) == 3 and args[0] in {"boolean", "null"}:
            return compatible(args[1:])
        if op == "coalesce" and 2 <= len(args) <= 16:
            return compatible(args)
        if op in {
            "trim",
            "lower",
            "upper",
            "length",
            "starts_with",
            "ends_with",
            "contains",
            "concat",
            "replace",
        }:
            arity = (
                3
                if op == "replace"
                else (2 if op in {"starts_with", "ends_with", "contains", "concat"} else 1)
            )
            valid_arity = 2 <= len(args) <= 16 if op == "concat" else len(args) == arity
            if not valid_arity or any(a not in {"string", "null"} for a in args):
                raise ValueError(
                    "String operations require string arguments and the correct arity."
                )
            return (
                "numeric"
                if op == "length"
                else ("boolean" if op in {"starts_with", "ends_with", "contains"} else "string")
            )
        raise ValueError("Unsupported operation or incorrect argument count.")

    def visit(name):
        if name in types:
            return types[name]
        if name in visiting:
            raise ValueError("Cyclic derived feature dependencies.")
        if len(visiting) >= 16:
            raise ValueError("Derived dependency depth exceeds bounded limit.")
        visiting.add(name)
        dependencies = []
        result = infer(definitions[name], dependencies)
        if result == "null":
            raise ValueError(
                "Derived output needs a numeric, boolean or string type; "
                "use a typed operation around null."
            )
        levels[name] = 1 + max(dependencies, default=0)
        if levels[name] > 16:
            raise ValueError("Derived dependency depth exceeds bounded limit.")
        visiting.remove(name)
        order.append(name)
        types[name] = result
        return result

    for name in definitions:
        visit(name)
    return order, types


def derived_transform(frame, config):
    """Append outputs; domain errors become missing, with row-level diagnostics.

    Nulls propagate except coalesce and Kleene logic. Unknown IF is missing.
    Numeric rounding uses NumPy ties-to-even; string outputs are capped at 4096.
    """
    if not isinstance(frame, pd.DataFrame) or not frame.columns.is_unique:
        raise ValueError("Derived features require uniquely named dataframe columns.")
    source_types = {}
    declared = config.get("input_types", {})
    for name in frame.columns:
        series = frame[name]
        if name in declared:
            source_types[name] = declared[name]
        elif pd.api.types.is_bool_dtype(series.dtype):
            source_types[name] = "boolean"
        elif pd.api.types.is_numeric_dtype(series.dtype):
            source_types[name] = "numeric"
        else:
            values = series.dropna()
            source_types[name] = (
                "boolean"
                if len(values) and values.map(lambda v: isinstance(v, (bool, np.bool_))).all()
                else "string"
            )
    # Runtime has physical columns for temporal outputs; references may use those.
    order, output_types = derived_validate(config, source_types, temporal_types=source_types)
    expected_outputs = config.get("output_types", {})
    if any(expected_outputs.get(name, kind) != kind for name, kind in output_types.items()):
        raise ValueError("Resolved derived output types do not match expressions.")
    definitions = {feature["name"]: feature["expression"] for feature in config.get("features", [])}
    cache, counts, inputs = {}, {}, {}
    index = frame.index

    def source(name):
        if name in inputs:
            return inputs[name]
        if name not in frame:
            raise ValueError("A required derived input column is absent.")
        value = frame[name]
        nonnull = value.dropna()
        kind = source_types[name]
        if kind == "numeric":
            valid = nonnull.map(
                lambda v: (
                    isinstance(v, (int, float, np.integer, np.floating))
                    and not isinstance(v, (bool, np.bool_))
                )
            ).all()
            if not valid:
                raise ValueError("Derived numeric input has incompatible values.")
            if nonnull.map(
                lambda v: (
                    isinstance(v, (int, np.integer))
                    and not isinstance(v, (bool, np.bool_))
                    and abs(int(v)) > 2**53 - 1
                )
            ).any():
                raise ValueError(
                    "Exact integer input is outside supported safe range; "
                    "use values between -(2**53 - 1) and 2**53 - 1."
                )
            value = value.astype(float)
            if not np.isfinite(value.dropna()).all():
                raise ValueError("Derived numeric input must contain finite values.")
        elif kind == "boolean":
            if not nonnull.map(
                lambda v: (
                    isinstance(v, (bool, np.bool_))
                    or (isinstance(v, (int, float, np.integer, np.floating)) and v in (0, 1))
                )
            ).all():
                raise ValueError("Derived boolean input has incompatible values.")
            value = value.astype("boolean")
        elif kind == "string":
            if not nonnull.map(lambda v: isinstance(v, str)).all():
                raise ValueError("Derived string input has incompatible values.")
            value = value.astype(object).where(value.notna(), np.nan)
        else:
            raise ValueError("Unsupported derived input type.")
        inputs[name] = value
        return value

    def evaluate(expression):
        kind = expression["kind"]
        invalid = pd.Series(False, index=index)
        if kind == "column":
            return source(expression["name"]), invalid
        if kind == "reference":
            return (
                cache[expression["name"]]
                if expression["name"] in cache
                else (source(expression["name"]), invalid)
            )
        if kind == "literal":
            literal = expression["value"]
            dtype = (
                "boolean"
                if type(literal) is bool
                else (float if type(literal) in (int, float) else object)
            )
            return pd.Series(
                np.nan if literal is None else literal, index=index, dtype=dtype
            ), invalid
        op = expression["operation"]
        evaluated = [evaluate(arg) for arg in expression["arguments"]]
        args = [arg[0] for arg in evaluated]
        for _, mask in evaluated:
            invalid |= mask
        left = args[0]
        missing = left.isna()
        for arg in args[1:]:
            missing |= arg.isna()
        with np.errstate(all="ignore"):
            if op in {
                "add",
                "subtract",
                "multiply",
                "safe_divide",
                "modulo",
                "power",
                "minimum",
                "maximum",
            }:
                right = args[1]
                function = {
                    "add": np.add,
                    "subtract": np.subtract,
                    "multiply": np.multiply,
                    "safe_divide": np.divide,
                    "modulo": np.remainder,
                    "power": np.power,
                    "minimum": np.minimum,
                    "maximum": np.maximum,
                }[op]
                value = pd.Series(function(left.astype(float), right.astype(float)), index=index)
                if op in {"safe_divide", "modulo"}:
                    value = value.mask(right == 0)
            elif op in {"abs", "negate", "sqrt", "log", "log1p", "round", "floor", "ceil"}:
                left = left.astype(float)
                if op == "round":
                    value = left.round(expression.get("parameters", {}).get("precision") or 0)
                else:
                    value = pd.Series(
                        {
                            "abs": np.abs,
                            "negate": np.negative,
                            "sqrt": np.sqrt,
                            "log": np.log,
                            "log1p": np.log1p,
                            "floor": np.floor,
                            "ceil": np.ceil,
                        }[op](left),
                        index=index,
                    )
            elif op in {
                "equal",
                "not_equal",
                "greater",
                "greater_equal",
                "less",
                "less_equal",
            }:
                method = {
                    "equal": "eq",
                    "not_equal": "ne",
                    "greater": "gt",
                    "greater_equal": "ge",
                    "less": "lt",
                    "less_equal": "le",
                }[op]
                value = getattr(left, method)(args[1]).astype("boolean").mask(missing)
            elif op in {"and", "or", "not"}:
                left = left.astype("boolean")
                value = (
                    ~left
                    if op == "not"
                    else (
                        left & args[1].astype("boolean")
                        if op == "and"
                        else left | args[1].astype("boolean")
                    )
                )
            elif op in {"is_missing", "is_not_missing"}:
                value = left.isna() if op == "is_missing" else left.notna()
            elif op == "if":
                condition = left.astype("boolean")
                value = args[1].where(condition.fillna(False), args[2]).mask(condition.isna())
                invalid = (
                    evaluated[0][1]
                    | evaluated[1][1].where(condition.fillna(False), False)
                    | evaluated[2][1].where((~condition).fillna(False), False)
                )
            elif op == "coalesce":
                value = left.copy()
                for arg in args[1:]:
                    value = value.where(value.notna(), arg)
                invalid &= value.isna()
            else:
                # Bounded literal string work; per-row substring operands are allowed.
                strings = [arg.astype("string") for arg in args]
                if op in {"trim", "lower", "upper", "length"}:
                    value = getattr(
                        strings[0].str, {"trim": "strip", "length": "len"}.get(op, op)
                    )()
                else:
                    # zip maps scalars only for operations pandas does not vectorize
                    # with per-row patterns; no regex or user code is executed.
                    def string_value(values):
                        if any(pd.isna(v) for v in values):
                            return np.nan
                        a, b = values[:2]
                        if op == "starts_with":
                            return a.startswith(b)
                        if op == "ends_with":
                            return a.endswith(b)
                        if op == "contains":
                            return b in a
                        if op == "concat":
                            return "".join(values) if sum(map(len, values)) <= 4096 else np.nan
                        replacement = values[2]
                        size = len(a) + (a.count(b) if b else len(a) + 1) * (
                            len(replacement) - len(b)
                        )
                        return a.replace(b, replacement) if size <= 4096 else np.nan

                    value = pd.Series(
                        map(string_value, zip(*strings, strict=True)), index=index, dtype=object
                    )
                value = pd.Series(value, index=index)
                if op not in {"length", "starts_with", "ends_with", "contains"}:
                    value = value.astype("string").mask(value.astype("string").str.len() > 4096)
                value = value.mask(missing)
            if pd.api.types.is_numeric_dtype(value.dtype) and not pd.api.types.is_bool_dtype(
                value.dtype
            ):
                value = value.astype(float).where(np.isfinite(value.astype(float)))
        if op not in {"and", "or", "not", "is_missing", "is_not_missing", "if", "coalesce"}:
            invalid |= value.isna() & ~missing
        return value, invalid

    result = frame.copy()
    for name in order:
        value, invalid = evaluate(definitions[name])
        kind = output_types[name]
        if kind in {"numeric", "boolean"}:
            value = value.astype(float)
        else:
            value = value.astype(object).where(value.notna(), np.nan)
        cache[name] = (value.astype("boolean") if kind == "boolean" else value, invalid)
        counts[name] = {
            "invalid_count": int(invalid.sum()),
            "missing_count": int(value.isna().sum()),
        }
    for name in definitions:
        value = cache[name][0]
        result[name] = value.astype(float) if output_types[name] == "boolean" else value
    return result, counts


class DerivedFeatures(TransformerMixin, BaseEstimator):
    """Stateless sklearn extension preserves raw inputs and appends declared outputs."""

    def __init__(self, config):
        self.config = config

    def fit(self, X, y=None):
        self.feature_names_in_ = np.asarray(X.columns, dtype=object)
        self.n_features_in_ = len(X.columns)
        return self

    def transform(self, X):
        return derived_transform(X, self.config)[0]

    def get_feature_names_out(self, input_features=None):
        names = self.feature_names_in_ if input_features is None else input_features
        return np.asarray(
            [*names, *[feature["name"] for feature in self.config["features"]]], dtype=object
        )


def register_derived_transformer():
    """Expose the fixed pickle module when frozen generated Python runs standalone."""
    import sys
    import types

    name = "mlstudio.derived_runtime_v1"
    if "mlstudio" not in sys.modules:
        parent = types.ModuleType("mlstudio")
        parent.__path__ = []
        sys.modules["mlstudio"] = parent
    if name not in sys.modules:
        module = types.ModuleType(name)
        module.DerivedFeatures = DerivedFeatures
        sys.modules[name] = module
        DerivedFeatures.__module__ = name
    return sys.modules[name].DerivedFeatures
