"""Portable single-column transforms. No learned full-dataset preview or refitting."""

import math

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.preprocessing import PowerTransformer, QuantileTransformer

from mlstudio.derived_runtime_v1 import derived_transform


class EngineeringValidationError(ValueError):
    pass


def engineering_key(value):
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (bool, np.bool_)):
        return ("boolean", bool(value))
    if isinstance(value, (int, float, np.integer, np.floating)):
        if isinstance(value, (int, np.integer)) and abs(int(value)) > 2**53 - 1:
            raise EngineeringValidationError(
                "Category integers exceed the supported exact scalar range."
            )
        if not math.isfinite(value):
            raise EngineeringValidationError("Category values must be finite.")
        return ("number", float(value))
    if isinstance(value, str):
        return ("string", value)
    raise EngineeringValidationError("Unsupported categorical scalar type.")


def engineering_fitted(feature):
    return feature["method"] in {
        "yeo_johnson",
        "box_cox",
        "quantile",
        "width",
        "quantile_bins",
        "rare",
    }


def engineering_semantic(feature):
    return (
        "categorical"
        if feature["method"] in {"boundaries", "width", "quantile_bins", "rare"}
        else "continuous"
    )


def engineering_validate(config, types, target=None):
    types = dict(types)
    names = set(types)
    outputs = set()
    for feature in config.get("features", []):
        name, source, method = feature["name"], feature["source"], feature["method"]
        if name in names or name in outputs:
            raise EngineeringValidationError(
                "Feature output name collides with an existing column or output."
            )
        if source == target or source not in types:
            raise EngineeringValidationError(
                "Choose an existing non-target source or temporal/derived feature; "
                "only earlier stateless engineering outputs may be chained."
            )
        if method not in {"rare", "ordinal"} and types[source] != "numeric":
            raise EngineeringValidationError("Numeric transformation requires a numeric input.")
        if method in {"rare", "ordinal"} and types[source] not in {"string", "numeric", "boolean"}:
            raise EngineeringValidationError("Choose a supported categorical input.")
        outputs.add(name)
        if not engineering_fitted(feature):
            types[name] = "string" if engineering_semantic(feature) == "categorical" else "numeric"


def engineering_numeric(series, coerce=False):
    if not pd.api.types.is_numeric_dtype(series.dtype) or pd.api.types.is_bool_dtype(series.dtype):
        raise EngineeringValidationError("Numeric transformation requires numeric source values.")
    if (
        pd.api.types.is_integer_dtype(series.dtype)
        and ((series.dropna() > 2**53 - 1) | (series.dropna() < -(2**53 - 1))).any()
    ):
        raise EngineeringValidationError(
            "Numeric integers exceed the supported exact scalar range."
        )
    values = series.to_numpy(dtype=float, na_value=np.nan)
    if coerce:
        return np.where(np.isinf(values), np.nan, values)
    if np.isinf(values).any():
        raise EngineeringValidationError("Numeric source values must be finite or missing.")
    return values


def engineering_stateless(frame, feature):
    method, source, name = feature["method"], feature["source"], feature["name"]
    series = frame[source]
    invalid = 0
    if method in {"log", "log1p", "sqrt", "reciprocal"}:
        numeric = engineering_numeric(series, feature.get("invalid") == "coerce")
        nonfinite = int(np.isinf(series.to_numpy(dtype=float, na_value=np.nan)).sum())
        if nonfinite:
            frame = frame.assign(**{source: numeric})
        argument = {"kind": "column", "name": source}
        expression = {
            "kind": "call",
            "operation": method,
            "arguments": [argument],
            "parameters": {},
        }
        if method == "reciprocal":
            expression.update(
                operation="safe_divide", arguments=[{"kind": "literal", "value": 1}, argument]
            )
        result, diagnostics = derived_transform(
            frame,
            {
                "version": "derived-v1",
                "features": [{"name": name, "expression": expression}],
                "input_types": {source: "numeric"},
                "output_types": {name: "numeric"},
            },
        )
        invalid = diagnostics[name]["invalid_count"] + nonfinite
        if invalid and feature.get("invalid", "reject") == "reject":
            raise EngineeringValidationError(
                f"{name}: {invalid} invalid numeric-domain values; "
                "clean inputs or explicitly mark invalid values as missing."
            )
        return result[name], invalid
    if method == "boundaries":
        values = engineering_numeric(series)
        result = (
            pd.Series(
                np.searchsorted(feature["boundaries"], values, side="right"), index=series.index
            )
            .map(lambda i: f"bin_{i}")
            .mask(series.isna())
        )
        return result, invalid
    if method == "ordinal":
        mapping = {engineering_key(item["value"]): item["code"] for item in feature["mapping"]}
        keys = series.map(engineering_key)
        unknown = keys.notna() & ~keys.isin(mapping)
        if unknown.any() and feature["unknown"] == "reject":
            raise EngineeringValidationError(
                f"{name}: unknown categories; extend the explicit mapping "
                "or change its unknown policy."
            )
        result = keys.map(
            lambda key: (
                np.nan
                if key is None
                else mapping.get(
                    key, feature.get("unknown_code") if feature["unknown"] == "code" else np.nan
                )
            )
        ).astype(float)
        return result, int(unknown.sum())
    raise EngineeringValidationError("Unsupported stateless feature transformation.")


def engineering_preview(frame, config):
    result = frame.copy()
    diagnostics = {}
    for feature in config.get("features", []):
        source, name, method = feature["source"], feature["name"], feature["method"]
        series = result[source]
        info = {
            "fitted": engineering_fitted(feature),
            "missing_count": int(series.isna().sum()),
            "invalid_count": 0,
            "message": "Stateless source preview.",
        }
        if info["fitted"]:
            info["message"] = (
                "Configuration only: parameters fit training rows exclusively. "
                "No transformed values are available before training."
            )
            if method == "rare" and series.nunique(dropna=True) > 1000:
                info["message"] += (
                    " High cardinality: review this input; fit rejects over 10000 categories."
                )
            if method != "rare":
                values = engineering_numeric(series)
                if method == "box_cox":
                    info["invalid_count"] = int(np.sum(values <= 0))
                    if info["invalid_count"]:
                        raise EngineeringValidationError(
                            "Box-Cox requires strictly positive observed inputs; "
                            "configure upstream cleaning."
                        )
            # Compatibility facts only, never estimate boundaries/frequencies/parameters.
        else:
            result[name], info["invalid_count"] = engineering_stateless(result, feature)
            info["missing_count"] = int(result[name].isna().sum())
        diagnostics[name] = info
    return result, diagnostics


class EngineeringFeatures(TransformerMixin, BaseEstimator):
    def __init__(self, config):
        self.config = config

    def fit(self, X, y=None):
        self.feature_names_in_ = np.asarray(X.columns, dtype=object)
        self.fitted_, self.diagnostics_ = {}, {}
        working = X.copy()
        for feature in self.config.get("features", []):
            name, method = feature["name"], feature["method"]
            series = working[feature["source"]]
            if not engineering_fitted(feature):
                working[name], _ = engineering_stateless(working, feature)
                continue
            if method == "rare":
                counts = {}
                for value in series:
                    key = engineering_key(value)
                    if key is not None:
                        counts[key] = counts.get(key, 0) + 1
                    if len(counts) > 10000:
                        raise EngineeringValidationError(
                            "Rare-category cardinality exceeds 10000; simplify the feature first."
                        )
                threshold = feature.get("min_count") or feature["min_frequency"] * len(X)
                retained = {key for key, count in counts.items() if count >= threshold}
                labels = {key: str(key[1]) for key in counts}
                if len(set(labels.values())) != len(labels):
                    raise EngineeringValidationError(
                        "Typed categorical labels collide after conversion to encoder-safe strings."
                    )
                if feature["rare_label"] in {labels[key] for key in retained}:
                    raise EngineeringValidationError(
                        "Rare label collides with a retained category; choose a distinct label."
                    )
                self.fitted_[name] = {"known": set(counts), "retained": retained, "labels": labels}
                continue
            values = engineering_numeric(series)
            observed = values[~np.isnan(values)]
            if len(observed) < 2 or len(np.unique(observed)) < 2:
                raise EngineeringValidationError(
                    f"{name}: fitting requires at least two distinct observed training values."
                )
            if method == "box_cox" and (observed <= 0).any():
                raise EngineeringValidationError(
                    "Box-Cox requires strictly positive training inputs; "
                    "configure upstream cleaning."
                )
            if method in {"yeo_johnson", "box_cox"}:
                fitted = PowerTransformer(method=method.replace("_", "-"), standardize=False)
            elif method == "quantile":
                fitted = QuantileTransformer(
                    n_quantiles=min(feature["quantiles"], len(observed)),
                    output_distribution=feature["distribution"],
                    subsample=None,
                    random_state=0,
                    copy=True,
                )
            else:
                count = feature["bins"]
                edges = (
                    np.linspace(observed.min(), observed.max(), count + 1)
                    if method == "width"
                    else np.quantile(observed, np.linspace(0, 1, count + 1))
                )
                edges = np.unique(edges)
                if not np.isfinite(edges).all():
                    raise EngineeringValidationError(
                        "Binning produced nonfinite boundaries; rescale source values."
                    )
                self.fitted_[name] = edges[1:-1]
                self.diagnostics_[name] = {"requested_bins": count, "actual_bins": len(edges) - 1}
                continue
            try:
                fitted.fit(observed.reshape(-1, 1))
            except (ValueError, FloatingPointError) as error:
                raise EngineeringValidationError(
                    f"{name}: degenerate training feature; "
                    "review its domain or use another transform."
                ) from error
            self.fitted_[name] = fitted
        return self

    def transform(self, X):
        if not hasattr(self, "fitted_"):
            raise EngineeringValidationError("Fit feature engineering before prediction.")
        result = X.copy()
        for feature in self.config.get("features", []):
            name, method, source = feature["name"], feature["method"], feature["source"]
            series = result[source]
            if not engineering_fitted(feature):
                result[name], _ = engineering_stateless(result, feature)
            elif method == "rare":
                state = self.fitted_[name]
                batch_labels = {text: key for key, text in state["labels"].items()}

                def label(value, state=state, feature=feature, name=name, seen=batch_labels):
                    key = engineering_key(value)
                    if key is None:
                        return np.nan
                    if key in state["retained"]:
                        return state["labels"][key]
                    if key not in state["known"]:
                        if feature["unknown"] == "reject":
                            raise EngineeringValidationError(
                                f"{name}: unknown category; review the unknown-category policy."
                            )
                        if feature["unknown"] == "preserve":
                            text = str(key[1])
                            if text == feature["rare_label"] or (
                                text in seen and seen[text] != key
                            ):
                                raise EngineeringValidationError(
                                    "Unseen category collides with an existing output label."
                                )
                            seen[text] = key
                            return text
                    return feature["rare_label"]

                result[name] = series.map(label)
            else:
                values = engineering_numeric(series)
                observed = ~np.isnan(values)
                if method in {"width", "quantile_bins"}:
                    result[name] = (
                        pd.Series(
                            np.searchsorted(self.fitted_[name], values, side="right"), index=X.index
                        )
                        .map(lambda i: f"bin_{i}")
                        .mask(series.isna())
                    )
                else:
                    if method == "box_cox" and (values[observed] <= 0).any():
                        raise EngineeringValidationError(
                            "Box-Cox requires strictly positive prediction inputs."
                        )
                    output = np.full(len(X), np.nan)
                    if observed.any():
                        with np.errstate(all="ignore"):
                            output[observed] = (
                                self.fitted_[name]
                                .transform(values[observed].reshape(-1, 1))
                                .ravel()
                            )
                    if not np.isfinite(output[observed]).all():
                        raise EngineeringValidationError(
                            "Transformation produced nonfinite output; review numeric input ranges."
                        )
                    result[name] = output
        return result

    def get_feature_names_out(self, input_features=None):
        return np.asarray(
            [
                *(self.feature_names_in_ if input_features is None else input_features),
                *[f["name"] for f in self.config.get("features", [])],
            ],
            dtype=object,
        )


def register_engineering_transformer():
    import sys
    import types

    name = "mlstudio.feature_engineering_runtime_v1"
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
                if key.startswith("engineering_")
                or key in {"EngineeringFeatures", "EngineeringValidationError"}
            }
        )
        sys.modules[name] = module
        EngineeringFeatures.__module__ = name
    return sys.modules[name].EngineeringFeatures
