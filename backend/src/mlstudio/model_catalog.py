"""Closed, descriptive built-ins. No estimator construction or import resolution."""

from dataclasses import dataclass

from mlstudio.pipeline_schemas import (
    ContextualConstraint,
    FeatureRequirements,
    ForestModel,
    LinearModel,
    LogisticModel,
    ModelDescriptor,
    PipelineIssue,
    RidgeModel,
    TreeModel,
)
from mlstudio.schemas import InputModel


def minimum(name, value, *, allow_none=False):
    return ContextualConstraint(
        minimum=value,
        allow_none=allow_none,
        message=f"{name} must be an integer of at least {value}.",
    )


TREE_CONSTRAINTS = {
    "max_depth": minimum("max_depth", 1, allow_none=True),
    "min_samples_split": minimum("min_samples_split", 2),
    "min_samples_leaf": minimum("min_samples_leaf", 1),
}


@dataclass(frozen=True)
class BuiltinModel:
    id: str
    task: str
    name: str
    intent_schema: type[InputModel]
    compiler_adapter: str
    contextual_constraints: dict[str, ContextualConstraint]

    def default_intent(self):
        return self.intent_schema(type=self.id)

    def descriptor(self):
        parameters = self.default_intent().parameters
        return ModelDescriptor(
            id=self.id,
            task=self.task,
            name=self.name,
            parameter_schema=type(parameters).model_json_schema(),
            defaults=parameters.model_dump(mode="json"),
            contextual_constraints={
                name: rule.model_copy(deep=True)
                for name, rule in self.contextual_constraints.items()
            },
            feature_requirements=FeatureRequirements(),
            compiler_adapter=self.compiler_adapter,
        )


BUILTINS = (
    BuiltinModel(
        "logistic_regression",
        "binary_classification",
        "Logistic Regression",
        LogisticModel,
        "sklearn-logistic-v1",
        {
            "C": ContextualConstraint(
                exclusive_minimum=0, message="C must be finite and greater than zero."
            ),
            "penalty": ContextualConstraint(choices=["l1", "l2"], message="Choose l1 or l2."),
            "max_iter": minimum("max_iter", 1),
        },
    ),
    BuiltinModel(
        "decision_tree",
        "binary_classification",
        "Decision Tree Classifier",
        TreeModel,
        "sklearn-tree-classifier-v1",
        TREE_CONSTRAINTS,
    ),
    BuiltinModel(
        "random_forest",
        "binary_classification",
        "Random Forest Classifier",
        ForestModel,
        "sklearn-forest-classifier-v1",
        {
            **TREE_CONSTRAINTS,
            "n_estimators": minimum("n_estimators", 1),
        },
    ),
    BuiltinModel(
        "linear_regression", "regression", "Linear Regression", LinearModel, "sklearn-linear-v2", {}
    ),
    BuiltinModel("ridge", "regression", "Ridge Regression", RidgeModel, "sklearn-ridge-v2", {}),
)


def entries(task):
    if task not in {"binary_classification", "regression"}:
        raise ValueError("Unsupported model catalogue task.")
    return tuple(entry for entry in BUILTINS if entry.task == task)


def model_catalogue(task):
    return [entry.descriptor() for entry in entries(task)]


def model_defaults(task):
    return [entry.default_intent() for entry in entries(task)]


def descriptor_for(model, task):
    return next((entry.descriptor() for entry in entries(task) if entry.id == model.type), None)


def model_parameter_issues(model, task):
    if model is None:
        return [
            PipelineIssue(
                scope="train",
                code="model_missing",
                message="Select a model in Train.",
                field="model",
            )
        ]
    descriptor = descriptor_for(model, task)
    if descriptor is None:
        return [
            PipelineIssue(
                scope="train",
                code="model_task",
                message="Model does not support this Project task.",
                field="model.type",
            )
        ]
    issues = []
    for name, rule in descriptor.contextual_constraints.items():
        value = getattr(model.parameters, name)
        if value is None:
            valid = rule.allow_none
        elif rule.choices is not None:
            valid = value in rule.choices
        elif rule.exclusive_minimum is not None:
            valid = value > rule.exclusive_minimum
        else:
            valid = value >= rule.minimum
        if not valid:
            issues.append(
                PipelineIssue(
                    scope="train",
                    code="model_parameter",
                    message=rule.message,
                    field=f"model.parameters.{name}",
                )
            )
    return issues
