"""Resolve all implementation choices before source rendering."""

from mlstudio.codegen.compatibility import library_versions, python_version
from mlstudio.codegen.schemas import (
    Constructor,
    EffectiveExecutionPlan,
    FeaturePlan,
    ImplementationContract,
    ResolvedSplit,
    SourceContract,
    TargetPlan,
)
from mlstudio.services.pipelines import validate


def operation(op):
    if op.type == "impute":
        return Constructor(
            name="SimpleImputer",
            parameters={
                "strategy": op.strategy,
                "missing_values": "nan",
                "copy": True,
                "add_indicator": False,
                "keep_empty_features": False,
            },
        )
    if op.type == "encode":
        return Constructor(
            name="OneHotEncoder",
            parameters={
                "categories": "auto",
                "drop": None,
                "handle_unknown": "ignore",
                "sparse_output": True,
                "dtype": "float64",
                "feature_name_combiner": "concat",
                "min_frequency": None,
                "max_categories": None,
            },
        )
    if op.method == "standard":
        return Constructor(
            name="StandardScaler",
            parameters={
                "copy": True,
                "with_mean": True,
                "with_std": True,
            },
        )
    if op.method == "min_max":
        return Constructor(
            name="MinMaxScaler",
            parameters={
                "feature_range": (0.0, 1.0),
                "copy": True,
                "clip": False,
            },
        )
    return Constructor(
        name="RobustScaler",
        parameters={
            "with_centering": True,
            "with_scaling": True,
            "quantile_range": (25.0, 75.0),
            "copy": True,
            "unit_variance": False,
        },
    )


def classifier(ir):
    parameters = ir.model.parameters.model_dump()
    if ir.model.type == "logistic_regression":
        parameters.update(
            solver="liblinear" if parameters["penalty"] == "l1" else "lbfgs",
            l1_ratio=1.0 if parameters["penalty"] == "l1" else 0.0,
            dual=False,
            tol=0.0001,
            fit_intercept=True,
            intercept_scaling=1,
            class_weight=None,
            random_state=ir.split.random_seed,
            verbose=0,
            warm_start=False,
        )
        return Constructor(name="LogisticRegression", parameters=parameters)
    parameters.update(
        criterion="gini",
        min_weight_fraction_leaf=0.0,
        max_leaf_nodes=None,
        min_impurity_decrease=0.0,
        class_weight=None,
        ccp_alpha=0.0,
        random_state=ir.split.random_seed,
        monotonic_cst=None,
    )
    if ir.model.type == "decision_tree":
        parameters.update(splitter="best", max_features=None)
        return Constructor(name="DecisionTreeClassifier", parameters=parameters)
    parameters.update(
        max_features="sqrt",
        bootstrap=True,
        oob_score=False,
        n_jobs=1,
        verbose=0,
        warm_start=False,
        max_samples=None,
    )
    return Constructor(name="RandomForestClassifier", parameters=parameters)


def resolve(ir, dataset, selected_target, frame):
    issues, classes, _, _ = validate(ir, dataset, selected_target, frame)
    if any(i.severity == "blocking" for i in issues):
        return None, issues
    columns = sorted(dataset.columns, key=lambda c: c["source_order"])
    target = next(c for c in columns if c["name"] == ir.target.column)
    plan = EffectiveExecutionPlan(
        dataset=ir.dataset,
        source=SourceContract(size_bytes=dataset.size_bytes),
        target=TargetPlan(
            column=ir.target.column,
            physical_dtype=str(frame[ir.target.column].dtype),
            semantic_type=target["semantic_override"] or target["inferred_semantic_type"],
            positive_class=ir.target.positive_class,
            negative_class=next(c for c in classes if c != ir.target.positive_class),
        ),
        features=tuple(
            FeaturePlan(
                name=c["name"],
                physical_dtype=str(frame[c["name"]].dtype),
                semantic_type=c["semantic_override"] or c["inferred_semantic_type"],
                operations=tuple(operation(op) for op in ir.features[c["name"]].operations),
            )
            for c in columns
            if c["name"] in ir.features and ir.features[c["name"]].included
        ),
        split=ResolvedSplit(**ir.split.model_dump()),
        model=classifier(ir),
        implementation=ImplementationContract(
            libraries=library_versions(), python=python_version()
        ),
    )
    return plan, issues
