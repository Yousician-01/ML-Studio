"""Portable stateless cleaning, with separate training-only row selection.

Conditional replacement selects its predicate instead of an exact match. Only
explicit true matches; unknown predicates are retained by a nonmatches filter.
No helpers consult a clock, learn statistics, or execute user-supplied code.
"""

import copy
import math
import re

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

from mlstudio.derived_runtime_v1 import derived_transform, derived_validate
from mlstudio.temporal_runtime_v1 import temporal_literal, temporal_parse


class CleaningValidationError(ValueError):
    """Sanitized configuration or data error; never contains source row values."""


def cleaning_dict(config):
    return config.model_dump(mode="json") if hasattr(config, "model_dump") else config


def cleaning_scalar(value):
    if value is None or type(value) is bool:
        return
    if type(value) is str and len(value) <= 1000:
        return
    if type(value) in (int, float):
        if (type(value) is not int or abs(value) <= 2**53 - 1) and math.isfinite(value):
            return
    raise CleaningValidationError("Cleaning constants must be bounded finite JSON scalars.")


def cleaning_bounds(config):
    config = cleaning_dict(config)
    if not isinstance(config, dict):
        raise CleaningValidationError("Invalid cleaning configuration.")
    steps = config.get("steps", [])
    if not isinstance(steps, list) or len(steps) > 64:
        raise CleaningValidationError("Cleaning steps exceed bounded limit.")
    total, identifiers = 0, set()
    for step in steps:
        step = cleaning_dict(step)
        if not isinstance(step, dict):
            raise CleaningValidationError("Invalid cleaning step.")
        identifier = step.get("id")
        if (
            not isinstance(identifier, str)
            or not 1 <= len(identifier) <= 80
            or identifier in identifiers
        ):
            raise CleaningValidationError("Cleaning step ids must be bounded and unique.")
        identifiers.add(identifier)
        if not isinstance(step.get("kind"), str) or step["kind"] not in {
            "normalize",
            "convert",
            "replace",
            "datetime_fill",
            "validate",
            "missing_filter",
            "filter",
            "deduplicate",
        }:
            raise CleaningValidationError("Unsupported cleaning operation.")
        if "columns" in step and not isinstance(step["columns"], list):
            raise CleaningValidationError("Cleaning columns must be a bounded list.")
        for option in ["destination", "invalid", "check", "action", "expected", "mode", "keep"]:
            if option in step and step[option] is not None and not isinstance(step[option], str):
                raise CleaningValidationError("Cleaning options require explicit supported values.")
        target = config.get("target")
        if target and (step.get("column") == target or target in step.get("columns", [])):
            raise CleaningValidationError("Cleaning cannot reference the supervised target.")
        condition = step.get("condition")
        stack = [] if condition is None else [(condition, 0)]
        nodes = 0
        while stack:
            node, depth = stack.pop()
            nodes += 1
            total += 1
            if not isinstance(node, dict) or depth > 8 or nodes > 256 or total > 4096:
                raise CleaningValidationError("Cleaning predicate exceeds total/depth/node bounds.")
            if (
                target
                and node.get("kind") in {"reference", "column"}
                and node.get("name") == target
            ):
                raise CleaningValidationError("Cleaning cannot reference the supervised target.")
            args = node.get("arguments", [])
            if not isinstance(args, list) or len(args) > 16:
                raise CleaningValidationError("Cleaning predicate argument limit exceeded.")
            stack.extend((arg, depth + 1) for arg in args)


def cleaning_types(frame, declared=None):
    aliases = {"continuous": "numeric", "categorical": "string", "binary": "boolean"}
    result = {}
    for name in frame:
        if declared and name in declared:
            result[name] = aliases.get(declared[name], declared[name])
        elif pd.api.types.is_bool_dtype(frame[name]):
            result[name] = "boolean"
        elif pd.api.types.is_numeric_dtype(frame[name]):
            result[name] = "numeric"
        elif pd.api.types.is_datetime64_any_dtype(frame[name]):
            result[name] = "datetime"
        else:
            observed = frame[name].dropna()
            result[name] = (
                "string"
                if observed.map(lambda value: isinstance(value, str)).all()
                else "unsupported"
            )
    return result


def cleaning_predicate(condition, input_types):
    expression = copy.deepcopy(condition)
    stack = [expression]
    while stack:
        node = stack.pop()
        if node.get("kind") == "reference":
            node["kind"] = "column"
        stack.extend(node.get("arguments", []))
    types = {name: "string" if kind == "datetime" else kind for name, kind in input_types.items()}
    name = "CleaningPredicate"
    while name in types:
        name += "X"
    return {
        "version": "derived-v1",
        "input_types": types,
        "features": [{"name": name, "expression": expression}],
    }, name


def cleaning_policy(policy):
    if not isinstance(policy, dict) or set(policy) - {"format", "naive", "invalid"}:
        raise CleaningValidationError("Invalid cleaning datetime policy.")
    fmt = policy.get("format", "ISO8601")
    if (
        not isinstance(fmt, str)
        or not 1 <= len(fmt) <= 100
        or (
            fmt != "ISO8601"
            and (
                not all(part in fmt for part in ["%Y", "%m", "%d"])
                or set(re.findall(r"%([A-Za-z%])", fmt)) - set("YmdHMSfz%")
            )
        )
    ):
        raise CleaningValidationError("Datetime parsing requires an explicit supported format.")
    if policy.get("naive", "reject") not in {"utc", "reject"} or policy.get(
        "invalid", "reject"
    ) not in {"reject", "coerce"}:
        raise CleaningValidationError("Invalid cleaning datetime policy.")


def cleaning_compatible(value, kind):
    cleaning_scalar(value)
    return value is None or (
        (kind == "numeric" and type(value) in (int, float))
        or (kind == "boolean" and type(value) is bool)
        or (kind in {"string", "datetime"} and type(value) is str)
    )


def cleaning_validate(config, source_types, target=None, selection_types=None):
    """Validate every stage against its available inputs; return corrected raw types."""
    config = cleaning_dict(config)
    cleaning_bounds(config)
    if config.get("version", "cleaning-v1") != "cleaning-v1":
        raise CleaningValidationError("Unsupported cleaning configuration version.")
    aliases = {"continuous": "numeric", "categorical": "string", "binary": "boolean"}
    types = {name: aliases.get(kind, kind) for name, kind in source_types.items()}
    target = target or config.get("target")
    identifiers = set()

    def column(name, available):
        if (
            not isinstance(name, str)
            or not 1 <= len(name) <= 200
            or name == target
            or available.get(name) not in {"numeric", "boolean", "string", "datetime"}
        ):
            raise CleaningValidationError(
                "Cleaning column is absent, unsupported, or the supervised target."
            )

    steps = config.get("steps", [])
    steps = [
        step for step in steps if step["kind"] not in {"missing_filter", "filter", "deduplicate"}
    ] + [step for step in steps if step["kind"] in {"missing_filter", "filter", "deduplicate"}]
    for step in steps:
        identifier, kind = step.get("id"), step.get("kind")
        if (
            not isinstance(identifier, str)
            or not 1 <= len(identifier) <= 80
            or identifier in identifiers
        ):
            raise CleaningValidationError("Cleaning step ids must be bounded and unique.")
        identifiers.add(identifier)
        selection = kind in {"missing_filter", "filter", "deduplicate"}
        available = {**types, **(selection_types or {})} if selection else types
        if kind in {"normalize", "convert", "replace", "datetime_fill", "validate"}:
            name = step.get("column")
            column(name, available)
            value_type = available[name]
        elif kind in {"missing_filter", "deduplicate"}:
            names = step.get("columns")
            if (
                not isinstance(names, list)
                or not 1 <= len(names) <= (16 if kind == "missing_filter" else 32)
                or any(not isinstance(name, str) for name in names)
                or len(set(names)) != len(names)
            ):
                raise CleaningValidationError("Cleaning selection columns exceed bounds or repeat.")
            for name in names:
                column(name, available)
        elif kind != "filter":
            raise CleaningValidationError("Unsupported cleaning operation.")
        predicate = step.get("condition")
        if predicate is not None:
            try:
                compiled, output = cleaning_predicate(predicate, available)
                _, inferred = derived_validate(compiled, compiled["input_types"], target)
                if inferred[output] != "boolean":
                    raise ValueError("Not boolean")
            except (ValueError, TypeError, KeyError) as exc:
                raise CleaningValidationError(
                    "Cleaning condition requires compatible boolean inputs "
                    "without target references."
                ) from exc
        if kind == "filter" and (
            predicate is None or step.get("keep", "matches") not in {"matches", "nonmatches"}
        ):
            raise CleaningValidationError("Invalid cleaning row filter.")
        if kind == "missing_filter" and (
            step.get("mode", "any") not in {"any", "all"}
            or step.get("keep", "present") not in {"missing", "present"}
        ):
            raise CleaningValidationError("Invalid cleaning missing-value filter.")
        if kind == "deduplicate" and step.get("keep", "first") not in {"first", "last"}:
            raise CleaningValidationError("Duplicate retention must be first or last.")
        if kind == "normalize":
            tokens = step.get("tokens")
            if (
                value_type not in {"string", "datetime"}
                or not isinstance(tokens, list)
                or len(tokens) > 32
                or any(type(value) is not str or len(value) > 1000 for value in tokens)
                or type(step.get("trim", False)) is not bool
                or type(step.get("case_sensitive", True)) is not bool
            ):
                raise CleaningValidationError(
                    "Missing-token normalization requires bounded string tokens "
                    "and a string or datetime column."
                )
        elif kind == "convert":
            destination = step.get("destination")
            if destination not in {"continuous", "categorical", "binary", "datetime"} or step.get(
                "invalid", "reject"
            ) not in {"reject", "coerce"}:
                raise CleaningValidationError("Unsupported cleaning type conversion.")
            cleaning_policy(step.get("policy", {}))
            types[name] = aliases.get(destination, destination)
        elif kind == "replace":
            if not cleaning_compatible(step.get("value"), value_type) or (
                predicate is None and not cleaning_compatible(step.get("match"), value_type)
            ):
                raise CleaningValidationError(
                    "Cleaning replacement constants have incompatible types."
                )
        elif kind == "datetime_fill":
            if value_type not in {"string", "datetime"}:
                raise CleaningValidationError(
                    "Datetime fill requires a raw datetime or string column."
                )
            cleaning_policy(step.get("policy", {}))
            try:
                cleaning_scalar(step.get("value"))
                if type(step.get("value")) is not str:
                    raise ValueError("Missing literal")
                temporal_literal(step["value"])
            except (ValueError, TypeError, OverflowError) as exc:
                raise CleaningValidationError(
                    "Datetime fill requires an explicit valid ISO timestamp or date."
                ) from exc
            types[name] = "datetime"
        elif kind == "validate":
            check = step.get("check")
            if check not in {"required", "range", "allowed", "length", "type"} or step.get(
                "action", "report"
            ) not in {"report", "reject", "coerce"}:
                raise CleaningValidationError("Unsupported cleaning validation rule.")
            minimum, maximum = step.get("minimum"), step.get("maximum")
            for bound in [minimum, maximum]:
                cleaning_scalar(bound)
                if bound is not None and type(bound) not in (int, float):
                    raise CleaningValidationError("Cleaning validation bounds must be numeric.")
            if minimum is not None and maximum is not None and minimum > maximum:
                raise CleaningValidationError("Cleaning validation range is reversed.")
            if check in {"range", "length"} and (minimum is None and maximum is None):
                raise CleaningValidationError("Cleaning validation requires at least one bound.")
            if check == "range" and value_type != "numeric":
                raise CleaningValidationError("Range validation requires a numeric column.")
            if check == "length" and (
                value_type not in {"string", "datetime"}
                or any(
                    bound is not None and (bound < 0 or int(bound) != bound)
                    for bound in [minimum, maximum]
                )
            ):
                raise CleaningValidationError(
                    "Length validation requires strings and nonnegative integer bounds."
                )
            values = step.get("values", [])
            if (
                not isinstance(values, list)
                or len(values) > 128
                or any(not cleaning_compatible(value, value_type) for value in values)
            ):
                raise CleaningValidationError(
                    "Allowed validation values have incompatible types or exceed bounds."
                )
            if check == "allowed" and not values:
                raise CleaningValidationError("Allowed validation requires explicit values.")
            if check == "type" and step.get("expected") not in {"numeric", "boolean", "string"}:
                raise CleaningValidationError(
                    "Type validation requires an explicit supported type."
                )
    return types


def cleaning_matches(frame, condition, types):
    if condition is None:
        return pd.Series(True, index=frame.index)
    predicate, name = cleaning_predicate(condition, types)
    try:
        result = derived_transform(frame, predicate)[0][name]
        return result.eq(1).fillna(False).astype(bool)
    except (ValueError, TypeError, KeyError) as exc:
        raise CleaningValidationError(
            "Cleaning predicate cannot evaluate supplied input types."
        ) from exc


def cleaning_exact(series, value):
    if value is None:
        return series.isna()
    if type(value) is bool:
        return series.map(lambda item: isinstance(item, (bool, np.bool_)) and bool(item) == value)
    if type(value) in (int, float):
        return series.map(
            lambda item: (
                not isinstance(item, (bool, np.bool_))
                and isinstance(item, (int, float, np.integer, np.floating))
                and item == value
            )
        )
    return series.map(lambda item: isinstance(item, str) and item == value)


def cleaning_convert(series, step):
    destination = step["destination"]
    if destination == "datetime":
        parsed, _ = temporal_parse(series, step.get("policy", {}))
        invalid = series.notna() & parsed.isna()
        return parsed.map(lambda value: None if pd.isna(value) else value.isoformat()), invalid
    if destination == "continuous":
        booleans = series.map(lambda value: isinstance(value, (bool, np.bool_)))
        output = pd.to_numeric(series.mask(booleans), errors="coerce").astype(float)
        finite = np.isfinite(output)
        # Keep integer conversion within the exact JSON/IEEE-754 safe range.
        unsafe = output.abs().gt(2**53 - 1) & output.eq(np.trunc(output))
        output = output.where(finite & ~unsafe)
    elif destination == "binary":

        def binary(value):
            if isinstance(value, (bool, np.bool_)):
                return bool(value)
            if isinstance(value, str):
                return {"true": True, "false": False, "1": True, "0": False}.get(value, pd.NA)
            if isinstance(value, (int, float, np.integer, np.floating)) and value in (0, 1):
                return bool(value)
            return pd.NA

        output = series.map(binary).astype("boolean")
    else:

        def categorical(value):
            if value is None or value is pd.NA or np.isscalar(value) and pd.isna(value):
                return None
            if isinstance(value, str):
                return value
            if isinstance(value, (bool, np.bool_)):
                return "true" if value else "false"
            if isinstance(value, (int, float, np.integer, np.floating)):
                if (
                    not np.isfinite(value)
                    or isinstance(value, (int, np.integer))
                    and abs(value) > 2**53 - 1
                ):
                    return None
                return str(value)
            return None

        output = series.map(categorical)
    return output, series.notna() & output.isna()


def cleaning_invalid(series, step):
    check = step["check"]
    if check == "required":
        return series.isna()
    if check == "allowed":
        valid = pd.Series(False, index=series.index)
        for value in step.get("values", []):
            valid |= cleaning_exact(series, value)
        return series.notna() & ~valid
    if check == "type":
        expected = step["expected"]

        def compatible(value):
            if expected == "boolean":
                return isinstance(value, (bool, np.bool_))
            if expected == "string":
                return isinstance(value, str)
            return (
                isinstance(value, (int, float, np.integer, np.floating))
                and not isinstance(value, (bool, np.bool_))
                and np.isfinite(value)
                and not (isinstance(value, (int, np.integer)) and abs(value) > 2**53 - 1)
            )

        return series.notna() & ~series.map(compatible)
    if check == "length":
        values = series.map(lambda value: len(value) if isinstance(value, str) else np.nan)
    else:
        values = series.map(
            lambda value: (
                value
                if isinstance(value, (int, float, np.integer, np.floating))
                and not isinstance(value, (bool, np.bool_))
                else np.nan
            )
        )
    invalid = series.notna() & (values.isna() | ~np.isfinite(values))
    if step.get("minimum") is not None:
        invalid |= series.notna() & values.lt(step["minimum"])
    if step.get("maximum") is not None:
        invalid |= series.notna() & values.gt(step["maximum"])
    return invalid


def cleaning_diagnostic(step, series, invalid, diagnostic):
    examples = []
    if diagnostic:
        for value in series[invalid].head(5):
            if isinstance(value, np.generic):
                value = value.item()
            if value is None or value is pd.NA or np.isscalar(value) and pd.isna(value):
                examples.append(None)
            elif type(value) in (str, bool, int, float):
                if type(value) is str:
                    examples.append(value[:1000])
                elif type(value) is not float or math.isfinite(value):
                    examples.append(value)
    count = int(invalid.sum())
    return {
        "id": step["id"],
        "column": step["column"],
        "invalid_count": count,
        "status": "invalid" if count else "ok",
        "examples": examples,
        "message": "Cleaning rule found invalid values." if count else "Cleaning rule completed.",
    }


def cleaning_transform(frame, config, *, diagnostic=False):
    """Execute raw stateless steps only; preserve every row and its index."""
    config = cleaning_dict(config)
    cleaning_bounds(config)
    raw = {
        **config,
        "steps": [
            step
            for step in config.get("steps", [])
            if step["kind"] not in {"filter", "missing_filter", "deduplicate"}
        ],
    }
    types = cleaning_types(frame, config.get("input_types"))
    cleaning_validate(raw, types, config.get("target"))
    result, diagnostics = frame.copy(), []
    for step in raw["steps"]:
        kind, name = step["kind"], step["column"]
        original = result[name].copy()
        invalid = pd.Series(False, index=result.index)
        reject = False
        if kind == "normalize":

            def token(value, step=step):
                value = value.strip() if step.get("trim", False) else value
                return value if step.get("case_sensitive", True) else value.casefold()

            tokens = {token(value) for value in step["tokens"]}
            matches = original.map(
                lambda value, token=token, tokens=tokens: (
                    isinstance(value, str) and token(value) in tokens
                )
            )
            result[name] = original.where(~matches, None)
        elif kind == "replace":
            matches = (
                cleaning_matches(result, step.get("condition"), types)
                if step.get("condition") is not None
                else cleaning_exact(original, step.get("match"))
            )
            result[name] = original.where(~matches, step.get("value"))
        elif kind == "convert":
            result[name], invalid = cleaning_convert(original, step)
            reject = step.get("invalid", "reject") == "reject"
            types[name] = {
                "continuous": "numeric",
                "categorical": "string",
                "binary": "boolean",
                "datetime": "datetime",
            }[step["destination"]]
        elif kind == "datetime_fill":
            parsed, _ = temporal_parse(original, step.get("policy", {}))
            invalid = original.notna() & parsed.isna()
            missing = original.isna() & cleaning_matches(result, step.get("condition"), types)
            parsed = parsed.where(~missing, temporal_literal(step["value"]))
            result[name] = parsed.map(lambda value: None if pd.isna(value) else value.isoformat())
            types[name] = "datetime"
            reject = step.get("policy", {}).get("invalid", "reject") == "reject"
        elif kind == "validate":
            invalid = cleaning_invalid(original, step)
            reject = step.get("action", "report") == "reject"
            if step.get("action", "report") == "coerce":
                result[name] = original.where(~invalid, None)
        diagnostics.append(cleaning_diagnostic(step, original, invalid, diagnostic))
        if invalid.any() and reject and not diagnostic:
            raise CleaningValidationError("Cleaning rule rejected invalid feature values.")
    return result, diagnostics


def cleaning_select(frame, config, *, diagnostic=False):
    """Training-only ordered selection; nonmatches retains unknown conditions."""
    config = cleaning_dict(config)
    cleaning_bounds(config)
    selection = {
        **config,
        "steps": [
            step
            for step in config.get("steps", [])
            if step["kind"] in {"filter", "missing_filter", "deduplicate"}
        ],
    }
    types = cleaning_types(frame, config.get("selection_types") or config.get("input_types"))
    # Conversions already happened. Infer their declared destination for predicates.
    for step in config.get("steps", []):
        if step["kind"] == "convert" and step["column"] in types:
            types[step["column"]] = {
                "continuous": "numeric",
                "categorical": "string",
                "binary": "boolean",
                "datetime": "datetime",
            }[step["destination"]]
    cleaning_validate(selection, types, config.get("target"))
    result, events = frame.copy(), []
    for step in selection["steps"]:
        before, kind = len(result), step["kind"]
        if kind == "deduplicate":
            result = result.loc[
                ~result.duplicated(subset=step["columns"], keep=step.get("keep", "first"))
            ]
        else:
            if kind == "missing_filter":
                missing = result[step["columns"]].isna()
                matches = (
                    missing.all(axis=1) if step.get("mode", "any") == "all" else missing.any(axis=1)
                )
                retain = matches if step.get("keep", "present") == "missing" else ~matches
            else:
                matches = cleaning_matches(result, step["condition"], types)
                retain = matches if step.get("keep", "matches") == "matches" else ~matches
            result = result.loc[retain]
        events.append(
            {
                "id": step["id"],
                "kind": kind,
                "before": before,
                "retained": len(result),
                "removed": before - len(result),
            }
        )
    return result, events


class CleaningFeatures(TransformerMixin, BaseEstimator):
    """Stateless row-wise inference transformer; never applies dataset selection."""

    def __init__(self, config):
        self.config = config

    def fit(self, X, y=None):
        self.feature_names_in_ = np.asarray(X.columns, dtype=object)
        self.n_features_in_ = len(X.columns)
        return self

    def transform(self, X):
        return cleaning_transform(X, self.config)[0]

    def get_feature_names_out(self, input_features=None):
        return np.asarray(
            self.feature_names_in_ if input_features is None else input_features, dtype=object
        )


def register_cleaning_transformer():
    """Register the fixed versioned class for trusted standalone model pickles."""
    import sys
    import types

    name = "mlstudio.cleaning_runtime_v1"
    if "mlstudio" not in sys.modules:
        parent = types.ModuleType("mlstudio")
        parent.__path__ = []
        sys.modules["mlstudio"] = parent
    if name not in sys.modules:
        module = types.ModuleType(name)
        module.__dict__.update(
            {
                key: value
                for key, value in globals().items()
                if key.startswith("cleaning_")
                or key in {"CleaningFeatures", "CleaningValidationError"}
            }
        )
        sys.modules[name] = module
        CleaningFeatures.__module__ = name
    return sys.modules[name].CleaningFeatures
