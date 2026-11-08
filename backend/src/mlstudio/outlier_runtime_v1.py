"""Portable training-only IQR fences and selected numeric branch variances."""

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.base import BaseEstimator, TransformerMixin, clone


class OutlierValidationError(ValueError):
    pass


def outlier_values(series, config):
    if not pd.api.types.is_numeric_dtype(series.dtype) or pd.api.types.is_bool_dtype(series.dtype):
        raise OutlierValidationError("Outlier treatment requires a continuous numeric input.")
    if (
        pd.api.types.is_integer_dtype(series.dtype)
        and ((series.dropna() > 2**53 - 1) | (series.dropna() < -(2**53 - 1))).any()
    ):
        raise OutlierValidationError("Outlier input integers exceed exact numeric precision.")
    values = series.to_numpy(dtype=float, na_value=np.nan)
    invalid = np.isinf(values)
    if invalid.any() and config["invalid"] == "reject":
        raise OutlierValidationError(
            "Outlier inputs contain nonfinite values; clean them or explicitly mark them missing."
        )
    values = np.where(invalid, np.nan, values)
    if np.isnan(values).any() and config["missing"] == "reject":
        raise OutlierValidationError(
            "Outlier inputs contain missing values; configure earlier imputation "
            "or preserve missingness."
        )
    return values


class OutlierFeatures(TransformerMixin, BaseEstimator):
    def __init__(self, config):
        self.config = config

    def fit(self, X, y=None):
        self.feature_names_in_ = np.asarray(X.columns, dtype=object)
        self.fences_, self.diagnostics_ = {}, {}
        for feature in self.config["features"]:
            values = outlier_values(X[feature["source"]], feature)
            observed = values[~np.isnan(values)]
            if len(observed) < 2:
                raise OutlierValidationError(
                    "IQR fitting requires at least two valid training observations."
                )
            with np.errstate(all="ignore"):
                q1, q3 = np.quantile(observed, [0.25, 0.75], method="linear")
                iqr = q3 - q1
                lower, upper = q1 - feature["multiplier"] * iqr, q3 + feature["multiplier"] * iqr
            if not np.isfinite([iqr, lower, upper]).all():
                raise OutlierValidationError(
                    "IQR fences exceed finite precision; rescale source values."
                )
            self.fences_[feature["name"]] = (float(lower), float(upper))
            self.diagnostics_[feature["name"]] = "zero_iqr" if iqr == 0 else "fitted"
        return self

    def transform(self, X):
        if not hasattr(self, "fences_"):
            raise OutlierValidationError("Fit outlier treatment before prediction.")
        result = X.copy()
        for feature in self.config["features"]:
            values = outlier_values(X[feature["source"]], feature)
            lower, upper = self.fences_[feature["name"]]
            lo = lower if feature["tails"] != "upper" else -np.inf
            hi = upper if feature["tails"] != "lower" else np.inf
            result[feature["name"]] = np.clip(values, lo, hi)
            if feature.get("indicator"):
                # Exactly the fitted treatment's fences and configured tails.
                result[feature["indicator"]] = np.where(
                    np.isnan(values), np.nan, ((values < lo) | (values > hi)).astype(float)
                )
        return result

    def get_feature_names_out(self, input_features=None):
        return np.asarray(
            [
                *(self.feature_names_in_ if input_features is None else input_features),
                *[
                    name
                    for f in self.config["features"]
                    for name in [f["name"], f.get("indicator")]
                    if name
                ],
            ],
            dtype=object,
        )


class SelectedPreprocessor(TransformerMixin, BaseEstimator):
    """Wrap the existing branches, selecting only explicitly eligible scalar outputs.

    Variance is population-ddof-0 AFTER each branch's configured imputation/scaling.
    Encoded categorical columns and ineligible numeric columns retain their order.
    """

    def __init__(self, preprocessor, config):
        self.preprocessor = preprocessor
        self.config = config

    def fit(self, X, y=None):
        self.fit_transform(X, y)
        return self

    def fit_transform(self, X, y=None, **fit_params):
        self.preprocessor_ = clone(self.preprocessor)
        matrix = self.preprocessor_.fit_transform(X, y)
        self.mask_ = np.ones(matrix.shape[1], dtype=bool)
        self.variances_, self.selected_features_ = {}, []
        for name, branch in self.config["branches"].items():
            section = self.preprocessor_.output_indices_[branch]
            if section.stop - section.start != 1:
                raise OutlierValidationError(
                    "Variance selection requires one numeric output per eligible feature; "
                    "review encoding or all-missing inputs."
                )
            column = matrix[:, section]
            values = (
                column.toarray().ravel()
                if sparse.issparse(column)
                else np.asarray(column, dtype=float).ravel()
            )
            if not len(values) or not np.isfinite(values).all():
                raise OutlierValidationError(
                    "Variance selection requires finite, nonmissing branch values; "
                    "configure imputation or clean inputs."
                )
            with np.errstate(all="ignore"):
                variance = float(np.var(values, ddof=0))
            if not np.isfinite(variance):
                raise OutlierValidationError(
                    "Variance exceeds finite precision; rescale the eligible feature."
                )
            self.variances_[name] = variance
            keep = variance > self.config["threshold"]
            self.mask_[section] = keep
            if keep:
                self.selected_features_.append(name)
        if not self.selected_features_:
            raise OutlierValidationError(
                "No eligible numeric features remain above the variance threshold; "
                "lower it or revise eligibility."
            )
        return matrix[:, self.mask_]

    def transform(self, X):
        if not hasattr(self, "mask_"):
            raise OutlierValidationError("Fit variance selection before prediction.")
        matrix = self.preprocessor_.transform(X)
        if matrix.shape[1] != len(self.mask_):
            raise OutlierValidationError(
                "Fitted feature width changed; restore the saved preprocessing pipeline."
            )
        return matrix[:, self.mask_]

    def get_feature_names_out(self, input_features=None):
        return self.preprocessor_.get_feature_names_out(input_features)[self.mask_]


def register_outlier_transformers():
    import sys
    import types

    name = "mlstudio.outlier_runtime_v1"
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
                if key.startswith("outlier_")
                or key in {"OutlierFeatures", "SelectedPreprocessor", "OutlierValidationError"}
            }
        )
        sys.modules[name] = module
        OutlierFeatures.__module__ = SelectedPreprocessor.__module__ = name
    module = sys.modules[name]
    return module.OutlierFeatures, module.SelectedPreprocessor
