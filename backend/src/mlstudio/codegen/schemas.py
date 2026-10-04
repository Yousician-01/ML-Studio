"""Derived, serializable execution evidence; never a second editable Pipeline IR."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from mlstudio.pipeline_schemas import DatasetBinding, PipelineIssue, TypedScalar

GENERATOR = "mlstudio-python-v1"


class PlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Constructor(PlanModel):
    name: Literal[
        "SimpleImputer",
        "StandardScaler",
        "MinMaxScaler",
        "RobustScaler",
        "OneHotEncoder",
        "LogisticRegression",
        "DecisionTreeClassifier",
        "RandomForestClassifier",
    ]
    parameters: dict[str, str | int | float | bool | None | tuple[float, float]]


class FeaturePlan(PlanModel):
    name: str
    physical_dtype: str
    semantic_type: Literal["continuous", "categorical", "binary"]
    operations: tuple[Constructor, ...]


class TargetPlan(PlanModel):
    column: str
    physical_dtype: str
    semantic_type: str
    positive_class: TypedScalar
    negative_class: TypedScalar
    missing_value_policy: Literal["exclude_rows"] = "exclude_rows"


class ResolvedSplit(PlanModel):
    test_size: float = Field(ge=0.05, le=0.5)
    random_seed: int = Field(ge=0, le=2147483647)
    stratify: bool


class SourceContract(PlanModel):
    parser: Literal["csv-utf8-v1"] = "csv-utf8-v1"
    size_bytes: int = Field(gt=0)
    encoding: Literal["utf-8-sig"] = "utf-8-sig"
    missing_values: Literal["pandas-default"] = "pandas-default"
    integer_policy: Literal["lossless-precision-risk-reread"] = "lossless-precision-risk-reread"


class ImplementationContract(PlanModel):
    version: Literal["sklearn-local-v1"] = "sklearn-local-v1"
    libraries: dict[str, str]
    python: str
    grouping: Literal["one-branch-per-feature-source-order"] = "one-branch-per-feature-source-order"
    remainder: Literal["drop"] = "drop"
    sparse_threshold: float = 1.0
    empty_training_feature: Literal["fail"] = "fail"


class RuntimeContract(PlanModel):
    version: Literal["cli-v1"] = "cli-v1"
    arguments: tuple[Literal["--dataset"], Literal["--result"], Literal["--model"]] = (
        "--dataset",
        "--result",
        "--model",
    )
    result_schema: Literal["mlstudio-result-v1"] = "mlstudio-result-v1"
    model_format: Literal["joblib-complete-pipeline"] = "joblib-complete-pipeline"


class EvaluationContract(PlanModel):
    metrics: tuple[
        Literal["accuracy"],
        Literal["precision"],
        Literal["recall"],
        Literal["f1"],
        Literal["roc_auc"],
    ] = ("accuracy", "precision", "recall", "f1", "roc_auc")
    zero_division: Literal[0] = 0
    confusion_order: Literal["negative-positive"] = "negative-positive"
    roc_auc: Literal["positive-score-or-unavailable"] = "positive-score-or-unavailable"


class EffectiveExecutionPlan(PlanModel):
    plan_version: Literal["0.1"] = "0.1"
    ir_version: Literal["0.1"] = "0.1"
    generator: Literal["mlstudio-python-v1"] = GENERATOR
    dataset: DatasetBinding
    source: SourceContract
    target: TargetPlan
    features: tuple[FeaturePlan, ...]
    split: ResolvedSplit
    model: Constructor
    implementation: ImplementationContract
    runtime: RuntimeContract = Field(default_factory=RuntimeContract)
    evaluation: EvaluationContract = Field(default_factory=EvaluationContract)


class CodePreview(PlanModel):
    context: Literal["working_pipeline"] = "working_pipeline"
    project_id: str
    revision: int
    dataset_id: str | None
    generator: str = GENERATOR
    ready: bool
    issues: list[PipelineIssue]
    source: str | None = None
    source_sha256: str | None = None
    plan_sha256: str | None = None
    filename: str = "generated_run.py"
    libraries: dict[str, str] = Field(default_factory=dict)
