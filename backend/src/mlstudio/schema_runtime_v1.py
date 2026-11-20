"""Portable shape/provenance guards. Existing runtimes own parsing and cleaning."""

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.base import BaseEstimator, TransformerMixin, clone


class SchemaContractError(ValueError):
    pass


class RawInputs(TransformerMixin, BaseEstimator):
    def __init__(self, contract):
        self.contract = contract

    def fit(self, X, y=None):
        self.transform(X)
        self.feature_names_in_ = np.asarray(X.columns, dtype=object)
        self.n_features_in_ = len(X.columns)
        return self

    def transform(self, X):
        if not isinstance(X, pd.DataFrame) or not X.columns.is_unique:
            raise SchemaContractError(
                "Raw prediction inputs require unique named DataFrame columns."
            )
        required = [column["name"] for column in self.contract["raw_inputs"]]
        missing = [name for name in required if name not in X]
        if missing:
            raise SchemaContractError("Required raw input columns missing: " + ", ".join(missing))
        # No coercion here: normalizers, explicit conversions and temporal parsers
        # must see the original scalar values. Extras can never shadow outputs.
        return X.loc[:, required].copy()

    def get_feature_names_out(self, input_features=None):
        return np.asarray([c["name"] for c in self.contract["raw_inputs"]], dtype=object)


class ContractPreprocessor(TransformerMixin, BaseEstimator):
    def __init__(self, preprocessor):
        self.preprocessor = preprocessor

    def fit(self, X, y=None):
        self.fit_transform(X, y)
        return self

    def fit_transform(self, X, y=None, **fit_params):
        self.preprocessor_ = clone(self.preprocessor)
        matrix = self.preprocessor_.fit_transform(X, y)
        names = self.preprocessor_.get_feature_names_out().tolist()
        mask = getattr(self.preprocessor_, "mask_", None)
        self.contract_ = {
            "version": "estimator-schema-v1",
            "feature_names": names,
            "feature_count": matrix.shape[1],
            "dtype": str(matrix.dtype),
            "representation": "sparse" if sparse.issparse(matrix) else "dense",
            "selected_mask": mask.tolist() if mask is not None else None,
        }
        self._validate(matrix, len(X))
        return matrix

    def _validate(self, matrix, rows):
        names = self.preprocessor_.get_feature_names_out().tolist()
        if names != self.contract_["feature_names"]:
            raise SchemaContractError(
                "Fitted transformed feature order changed; restore the model artifact."
            )
        if (
            matrix.ndim != 2
            or matrix.shape != (rows, self.contract_["feature_count"])
            or len(names) != matrix.shape[1]
        ):
            raise SchemaContractError(
                "Transformed feature count or row cardinality differs from the fitted contract."
            )
        values = matrix.data if sparse.issparse(matrix) else np.asarray(matrix)
        try:
            numeric = np.issubdtype(values.dtype, np.number) or np.issubdtype(
                values.dtype, np.bool_
            )
            if values.dtype == object:
                numeric = all(
                    isinstance(value, (int, float, bool, np.number, np.bool_))
                    for value in values.ravel()
                )
                if numeric:
                    values = values.astype(float)
            valid = numeric and np.isfinite(values).all()
        except (TypeError, ValueError, OverflowError):
            valid = False
        if not valid:
            raise SchemaContractError(
                "Estimator inputs contain missing/nonfinite or nonnumeric values; "
                "configure compatible cleaning, imputation and encoding."
            )

    def transform(self, X):
        if not hasattr(self, "contract_"):
            raise SchemaContractError("Fit the preprocessing contract before prediction.")
        matrix = self.preprocessor_.transform(X)
        self._validate(matrix, len(X))
        return matrix

    def get_feature_names_out(self, input_features=None):
        return np.asarray(self.contract_["feature_names"], dtype=object)


def register_schema_transformers():
    import sys
    import types

    name = "mlstudio.schema_runtime_v1"
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
                if key in {"RawInputs", "ContractPreprocessor", "SchemaContractError"}
            }
        )
        sys.modules[name] = module
        RawInputs.__module__ = ContractPreprocessor.__module__ = name
    module = sys.modules[name]
    return module.RawInputs, module.ContractPreprocessor
