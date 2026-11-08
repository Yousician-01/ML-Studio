"""Working intent validation and revision-guarded persistence, never execution."""

import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype
from sqlalchemy import select

from mlstudio.codegen.compatibility import compatibility_issues
from mlstudio.model_catalog import descriptor_for, model_catalogue, model_defaults
from mlstudio.models import Dataset, Project, utc_now
from mlstudio.pipeline_schemas import (
    PipelineIR,
    PipelineIssue,
    PipelineResponse,
    RegressionSplitIntent,
    TypedScalar,
    load_ir,
)
from mlstudio.services.artifacts import verified_source
from mlstudio.services.pipeline_state import column_role, initialize
from mlstudio.services.source import DomainError, json_scalar, parse_source
from mlstudio.services.task_policies import validate_target_for_task
from mlstudio.services.train_validation import partition_sizes, train_issues


def typed_scalar(value) -> TypedScalar:
    value = json_scalar(value)
    if isinstance(value, dict):
        return TypedScalar(**value)
    kind = {str: "string", int: "integer", float: "float", bool: "boolean"}[type(value)]
    return TypedScalar(value_type=kind, value=value)


def validate(ir: PipelineIR, dataset, selected_target, frame):
    issues = []
    engineering_diagnostics = {}
    original_dataset, original_frame = dataset, frame
    if (
        (ir.temporal is not None or ir.derived is not None or ir.cleaning is not None)
        and dataset is not None
        and ir.dataset is not None
        and (ir.dataset.dataset_id == dataset.id and ir.dataset.fingerprint == dataset.fingerprint)
    ):
        from mlstudio.services.derived import context
        from mlstudio.services.temporal import warnings

        try:
            dataset, frame, _, errors = context(ir, dataset, frame)
            if ir.cleaning is not None and not errors:
                from mlstudio.services.cleaning import selection

                frame, _ = selection(ir, original_dataset, original_frame, dataset, frame)
        except (ValueError, KeyError, TypeError):
            errors = [
                "Invalid cleaning, temporal or derived expressions, "
                "references or parsing policies. "
                "Review the feature preview."
            ]
        issues.extend(
            PipelineIssue(
                scope="pipeline",
                code="cleaning_invalid"
                if ir.cleaning is not None
                else "derived_invalid"
                if ir.derived is not None
                else "temporal_invalid",
                message=message,
            )
            for message in errors
        )
        if errors:
            return issues, [], 0, False
        issues.extend(
            PipelineIssue(
                scope="pipeline", code="temporal_leakage", message=message, severity="non_blocking"
            )
            for message in (
                warnings()
                if ir.temporal is not None
                else [
                    "Confirm expression inputs are available at prediction time. "
                    "Row-wise validation cannot detect all semantic leakage."
                ]
            )
        )
    if (
        ir.imputation is not None
        and dataset is not None
        and ir.dataset is not None
        and ir.dataset.dataset_id == dataset.id
        and ir.dataset.fingerprint == dataset.fingerprint
    ):
        from mlstudio.services.imputation import context as imputation_context

        try:
            dataset, frame, _ = imputation_context(ir, dataset, frame)
        except (ValueError, KeyError, TypeError) as error:
            issues.append(
                PipelineIssue(
                    scope="pipeline",
                    code="imputation_invalid",
                    message=str(error)
                    if isinstance(error, ValueError)
                    else "Invalid advanced imputation references.",
                )
            )
            return issues, [], 0, False
        issues.append(
            PipelineIssue(
                scope="pipeline",
                code="imputation_fitted",
                severity="non_blocking",
                message="Advanced statistics fit training rows only. "
                "Unresolved missing values fail training; "
                "no full-source fitted preview is available.",
            )
        )
    if (
        ir.feature_engineering is not None
        and dataset is not None
        and ir.dataset is not None
        and ir.dataset.dataset_id == dataset.id
        and ir.dataset.fingerprint == dataset.fingerprint
    ):
        from mlstudio.services.feature_engineering import context as engineering_context

        try:
            dataset, frame, engineering_diagnostics = engineering_context(ir, dataset, frame)
        except (ValueError, KeyError, TypeError) as error:
            issues.append(
                PipelineIssue(
                    scope="pipeline",
                    code="engineering_invalid",
                    message=str(error)
                    if isinstance(error, ValueError)
                    else "Invalid feature engineering references.",
                )
            )
            return issues, [], 0, False
    if (
        (ir.outlier_treatment is not None or ir.feature_selection is not None)
        and dataset is not None
        and ir.dataset is not None
        and ir.dataset.dataset_id == dataset.id
        and ir.dataset.fingerprint == dataset.fingerprint
    ):
        from mlstudio.services.outliers import context as outlier_context
        from mlstudio.services.outliers import validate_selection

        try:
            dataset, frame, _ = outlier_context(ir, dataset, frame)
            validate_selection(ir, dataset, frame)
        except (ValueError, KeyError, TypeError) as error:
            issues.append(
                PipelineIssue(
                    scope="pipeline",
                    code="outlier_selection_invalid",
                    message=str(error)
                    if isinstance(error, ValueError)
                    else "Invalid outlier or selection references.",
                )
            )
            return issues, [], 0, False
    regression = ir.ir_version == "0.2"
    multiclass = ir.ir_version == "0.3"
    task = (
        "multiclass_classification"
        if multiclass
        else "regression"
        if regression
        else "binary_classification"
    )

    def issue(code, message, scope="pipeline", column=None, dormant=False):
        field = None
        if regression:
            if scope == "target":
                field = "target.column"
            elif column:
                field = f"features.{column}.operations"
            else:
                field = "dataset" if code.startswith("dataset_") else "features"
        issues.append(
            PipelineIssue(
                code=code,
                message=message,
                scope=scope,
                column=column,
                field=field,
                severity="non_blocking" if dormant else "blocking",
            )
        )

    target_series = (
        frame[ir.target.column]
        if dataset is not None and ir.target and ir.target.column in frame
        else None
    )
    if not regression:
        issues.extend(train_issues(ir, target_series))
    if dataset is None:
        if regression:
            issues.extend(train_issues(ir, None))
        issue("dataset_missing", "Upload a Dataset in Data.")
        return issues, [], 0, False
    stale = ir.dataset is not None and (
        ir.dataset.dataset_id != dataset.id or ir.dataset.fingerprint != dataset.fingerprint
    )
    if stale:
        if regression:
            issues.extend(train_issues(ir, None))
        issue(
            "dataset_stale", "Dataset changed. Explicitly reset preparation for the current source."
        )
        return issues, [], 0, True
    if ir.dataset is None:
        issue("dataset_missing", "Initialize preparation for the current Dataset.")
    if regression:
        issues.extend(train_issues(ir, target_series))
    descriptor = descriptor_for(ir.model, task) if ir.model else None
    columns = {c["name"]: c for c in dataset.columns}
    classes, missing = [], 0
    if ir.target is None:
        issue(
            "target_missing",
            "Select a numeric target in Data."
            if regression
            else "Select a multiclass target in Data."
            if multiclass
            else "Select a binary target in Data.",
            "target",
        )
    else:
        name = ir.target.column
        if name != selected_target:
            issue(
                "target_context",
                "Target differs from Data. Restore the selected target context.",
                "target",
            )
        if name not in columns:
            issue("target_missing_column", "The configured target column is absent.", "target")
        else:
            series = frame[name]
            missing = int(series.isna().sum())
            if multiclass:
                try:
                    column = columns[name]
                    classes = [
                        typed_scalar(v)
                        for v in validate_target_for_task(
                            frame,
                            name,
                            task,
                            semantic_type=column["semantic_override"]
                            or column["inferred_semantic_type"],
                        )
                    ]
                except DomainError as error:
                    issue("target_not_multiclass", error.message, "target")
            elif regression:
                try:
                    validate_target_for_task(frame, name, "regression")
                except DomainError as error:
                    issue("target_not_numeric", error.message, "target")
            elif series.nunique() != 2:
                issue(
                    "target_not_binary",
                    "Target must contain exactly two non-missing classes.",
                    "target",
                )
            else:
                classes = [typed_scalar(v) for v in series.dropna().unique()]
            if regression or multiclass:
                pass  # Numeric targets have no class orientation.
            elif ir.target.positive_class is None:
                issue("positive_class_missing", "Choose the positive class explicitly.", "target")
            elif ir.target.positive_class not in classes:
                issue(
                    "positive_class_invalid",
                    "Positive class must match an observed class and its type.",
                    "target",
                )
    target = ir.target.column if ir.target else None
    for name in columns:
        if (
            name != target
            and name not in ir.features
            and columns[name].get("inference_version") != "imputation-v1"
        ):
            issue(
                "feature_missing",
                "Column is missing from the feature map. Reset or restore its configuration.",
                "feature",
                name,
            )
    if not any(
        f.included and name in columns and name != target for name, f in ir.features.items()
    ):
        issue("features_empty", "Include at least one usable feature.")
    for name, feature in ir.features.items():
        if name not in columns:
            issue(
                "feature_absent",
                "Configured column does not exist in this Dataset.",
                "feature",
                name,
            )
            continue
        if name == target or name == selected_target:
            issue(
                "target_feature", "The target must be absent from the feature map.", "feature", name
            )
        if columns[name].get("inference_version") == "imputation-v1":
            issue(
                "indicator_stage",
                "Missingness indicators are automatic advanced-stage outputs; "
                "do not configure earlier feature operations for them.",
                "feature",
                name,
            )
        semantic = columns[name]["semantic_override"] or columns[name]["inferred_semantic_type"]
        numeric = is_numeric_dtype(frame[name].dtype) and not is_bool_dtype(frame[name].dtype)
        dormant = not feature.included

        def feature_issue(code, message, name=name, dormant=dormant):
            issue(code, message, "feature", name, dormant)

        supported_semantics = (
            descriptor.feature_requirements.supported_semantics
            if descriptor
            else ["continuous", "categorical", "binary"]
        )
        if semantic not in supported_semantics:
            if feature.included:
                feature_issue(
                    "unsupported_semantic",
                    "Unsupported v0.1 feature type. Exclude it or review its meaning in Data.",
                )
            elif feature.operations:
                feature_issue(
                    "dormant_unsupported",
                    "Incompatible operations are retained but dormant.",
                )
        if semantic == "continuous" and not numeric:
            if feature.included or feature.operations:
                feature_issue(
                    "physical_mismatch",
                    "Continuous preparation requires numeric source values.",
                )
        families = [op.type for op in feature.operations]
        if len(families) != len(set(families)):
            feature_issue("duplicate_operation", "Each operation family may occur at most once.")
        if "impute" in families and families[0] != "impute":
            feature_issue("operation_order", "Imputation must precede scaling or encoding.")
        if "scale" in families and "encode" in families:
            feature_issue(
                "operation_combination", "Scaling and encoding cannot share one feature sequence."
            )
        # Model input compatibility is separate from semantic operation grammar.
        # Inspect eligible source facts only; never fit or split feature matrices.
        if feature.included and ir.model is not None and target_series is not None:
            observed = frame.loc[target_series.notna(), name]
            advanced = ir.imputation.columns.get(name) if ir.imputation else None
            if advanced is None and ir.imputation and ir.feature_engineering:
                upstream = next(
                    (f.source for f in ir.feature_engineering.features if f.name == name), None
                )
                if engineering_diagnostics.get(name, {}).get("invalid_count", 0) == 0:
                    advanced = ir.imputation.columns.get(upstream)
            if (
                not observed.empty
                and observed.count() == 0
                and not (advanced and advanced.fallback.strategy == "constant")
            ):
                issue(
                    "feature_all_missing",
                    "No observed feature values remain after target "
                    "exclusion. Exclude this feature or review its source.",
                    "train",
                    name,
                )
            elif (
                observed.isna().any()
                and "impute" not in families
                and advanced is None
                and descriptor
                and descriptor.feature_requirements.requires_complete_features
            ):
                issue(
                    "feature_missing_values",
                    "Configure imputation in Prepare. This configuration requires complete inputs.",
                    "train",
                    name,
                )
            if (
                not (numeric or is_bool_dtype(frame[name].dtype))
                and "encode" not in families
                and descriptor
                and descriptor.feature_requirements.requires_numeric_input
            ):
                issue(
                    "feature_encoding",
                    "Non-numeric model input requires one-hot encoding in Prepare.",
                    "train",
                    name,
                )
        for op in feature.operations:
            compatible = (
                (
                    op.type == "impute"
                    and (
                        semantic == "continuous"
                        and numeric
                        or semantic in {"categorical", "binary"}
                        and op.strategy == "most_frequent"
                    )
                )
                or (op.type == "scale" and semantic == "continuous" and numeric)
                or (op.type == "encode" and semantic in {"categorical", "binary"})
            )
            if not compatible:
                feature_issue(
                    "operation_incompatible",
                    f"{op.type.capitalize()} is incompatible with this semantic/physical type.",
                )
    issues.extend(compatibility_issues(ir, dataset, frame))
    return issues, classes, missing, stale


def snapshot(session, project_id):
    return session.execute(
        select(Project, Dataset)
        .outerjoin(Dataset, Dataset.id == Project.active_dataset_id)
        .where(Project.id == project_id)
        .execution_options(populate_existing=True)
    ).one()


def response(project, dataset, settings):
    frame = parse_source(verified_source(settings.home, dataset)) if dataset else pd.DataFrame()
    try:
        ir = load_ir(project.working_pipeline, project.ml_objective)
    except ValueError:
        raise DomainError(
            "Stored Pipeline version/task is unsupported. Reset preparation."
        ) from None
    issues, classes, missing, stale = validate(ir, dataset, project.target_column, frame)
    columns = (
        [
            {
                **c,
                "effective_semantic_type": c["semantic_override"] or c["inferred_semantic_type"],
                "role": column_role(project, dataset, c["name"]),
            }
            for c in dataset.columns
        ]
        if dataset
        else []
    )
    if (
        (
            ir.temporal is not None
            or ir.derived is not None
            or ir.imputation is not None
            or ir.cleaning is not None
            or ir.feature_engineering is not None
            or ir.outlier_treatment is not None
            or ir.feature_selection is not None
        )
        and dataset is not None
        and not stale
    ):
        from mlstudio.services.derived import context

        try:
            virtual, expanded, _, _ = context(ir, dataset, frame)
            if ir.feature_engineering is not None and ir.cleaning is not None:
                from mlstudio.services.cleaning import selection

                expanded, _ = selection(ir, dataset, frame, virtual, expanded)
            if ir.imputation is not None:
                from mlstudio.services.imputation import context as imputation_context

                virtual, expanded, _ = imputation_context(ir, virtual, expanded)
            if ir.feature_engineering is not None:
                from mlstudio.services.feature_engineering import context as engineering_context

                virtual, expanded, _ = engineering_context(ir, virtual, expanded)
            if ir.outlier_treatment is not None:
                from mlstudio.services.outliers import context as outlier_context

                virtual, expanded, _ = outlier_context(ir, virtual, expanded)
            if ir.cleaning is not None:
                columns = [
                    {
                        **c,
                        "effective_semantic_type": c["semantic_override"]
                        or c["inferred_semantic_type"],
                        "role": column_role(project, dataset, c["name"]),
                    }
                    for c in virtual.columns[: len(dataset.columns)]
                ]
            columns.extend(
                {
                    **c,
                    "effective_semantic_type": c["inferred_semantic_type"],
                    "role": "feature"
                    if c.get("inference_version") == "imputation-v1"
                    or (ir.features.get(c["name"]) and ir.features[c["name"]].included)
                    else "excluded",
                }
                for c in virtual.columns[len(dataset.columns) :]
            )
        except (ValueError, KeyError, TypeError):
            pass  # The invalid definitions remain persisted and carry blocking issues.
    eligible = (
        int(frame[ir.target.column].count()) if ir.target and ir.target.column in frame else 0
    )
    if ir.cleaning is not None and dataset is not None and not stale and ir.target:
        from mlstudio.services.cleaning import population

        try:
            eligible = population(ir, dataset, frame)["eligible"]
        except (ValueError, KeyError, TypeError):
            eligible = 0
    train_rows, test_rows = partition_sizes(eligible, ir.split)
    regression = ir.ir_version == "0.2"
    if regression and stale:
        eligible, train_rows, test_rows = 0, None, None
    configuration_ready = not any(i.severity == "blocking" for i in issues)
    return PipelineResponse(
        revision=project.revision,
        ir=ir,
        columns=columns,
        target_classes=classes,
        target_missing_count=missing,
        issues=issues,
        configuration_ready=configuration_ready,
        code_generation_ready=not any(i.severity == "blocking" for i in issues),
        original_filename=dataset.original_filename if dataset else None,
        eligible_rows=eligible,
        train_rows=train_rows,
        test_rows=test_rows,
        model_defaults=model_defaults(project.ml_objective),
        model_catalogue=model_catalogue(project.ml_objective),
        split_defaults=RegressionSplitIntent() if ir.ir_version == "0.2" else {},
        prepare_valid=not any(i.severity == "blocking" and i.scope != "train" for i in issues),
        stale=stale,
    )


def read(session, project, settings):
    project, dataset = snapshot(session, project.id)
    return response(project, dataset, settings)


def save(session, project, body, settings, reset=False):
    from mlstudio.services.code_drafts import require_visual_mode

    require_visual_mode(session, project.id)
    project, dataset = snapshot(session, project.id)
    if body.revision != project.revision:
        raise DomainError("Project changed. Reload the workspace before saving again.", 409)
    if reset:
        if dataset is None or body.dataset_id != dataset.id:
            raise DomainError("Dataset changed. Reload before resetting preparation.", 409)
        project.working_pipeline = initialize(
            dataset, project.target_column, objective=project.ml_objective
        )
    else:
        # Binding changes are deliberate reset operations, never generic edit side effects.
        try:
            load_ir(body.ir.model_dump(mode="json"), project.ml_objective)
            current = load_ir(project.working_pipeline, project.ml_objective)
        except ValueError:
            raise DomainError("Pipeline version/task must match the Project objective.") from None
        if body.ir.dataset != current.dataset:
            raise DomainError("Use explicit reset to change the Dataset binding.", 409)
        project.working_pipeline = body.ir.model_dump(mode="json")
    project.updated_at = utc_now()
    session.flush()  # Existing ORM version guard also catches concurrent DB transactions.
    result = response(project, dataset, settings)
    session.commit()
    return result
