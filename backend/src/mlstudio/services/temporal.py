"""Source-bound temporal validation and bounded preview; never persists raw rows."""

from types import SimpleNamespace

from pydantic import Field

from mlstudio.schemas import InputModel, Scalar
from mlstudio.temporal_runtime_v1 import temporal_transform
from mlstudio.temporal_schemas import ResolvedTemporalConfig, validate_temporal


class TemporalPreviewColumn(InputModel):
    name: str
    semantic_type: str
    missing_count: int
    values: list[Scalar]
    invalid_count: int = 0
    physical_dtype: str = "float64"


class ParsingCounts(InputModel):
    missing_count: int
    invalid_count: int
    date_only_count: int


class ImputationDiagnostics(InputModel):
    missing_count: int = Field(ge=0)
    rule_matches: list[int] = Field(max_length=16)
    indicator_values: list[float] = Field(max_length=20)


class CleaningColumn(InputModel):
    name: str
    physical_dtype: str
    semantic_type: str
    missing_count: int
    unique_count: int


class CleaningDiagnostic(InputModel):
    id: str
    column: str | None = None
    invalid_count: int
    status: str
    message: str
    examples: list[Scalar] = Field(default_factory=list, max_length=5)


class CleaningEvent(InputModel):
    id: str
    kind: str
    before: int
    retained: int
    removed: int


class CleaningPreview(InputModel):
    columns: list[CleaningColumn]
    rows: list[list[Scalar]] = Field(max_length=20)
    row_indices: list[int] = Field(max_length=20)
    source_rows: int
    retained_rows: int
    removed_rows: int
    events: list[CleaningEvent]
    diagnostics: list[CleaningDiagnostic]


class TemporalPreview(InputModel):
    revision: int
    cleaning: CleaningPreview | None = None
    imputation: dict[str, ImputationDiagnostics] = Field(default_factory=dict)
    limit: int = 20
    columns: list[TemporalPreviewColumn] = Field(default_factory=list)
    sources: dict[str, ParsingCounts] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


def context(ir, dataset, frame):
    semantics = {
        c["name"]: c["semantic_override"] or c["inferred_semantic_type"] for c in dataset.columns
    }
    from mlstudio.services.cleaning import temporal_config

    config = temporal_config(ir)
    _, types = validate_temporal(config, semantics, ir.target.column if ir.target else None)
    expanded, counts = temporal_transform(frame, config.model_dump(mode="json"), diagnostic=True)
    errors = [
        f"Datetime source {name}: {count['invalid_count']} invalid/disallowed values; "
        "correct the parsing policy or explicitly choose coerce to missing."
        for name, count in counts.items()
        if count["invalid_count"] and ir.temporal.sources[name].invalid == "reject"
    ]
    columns = list(dataset.columns)
    for index, feature in enumerate(ir.temporal.features):
        series = expanded[feature.name]
        columns.append(
            {
                "name": feature.name,
                "source_order": len(dataset.columns) + index,
                "physical_dtype": "float64",
                "missing_count": int(series.isna().sum()),
                "unique_count": int(series.nunique()),
                "inferred_semantic_type": types[feature.name][0],
                "semantic_override": None,
                "inference_version": "temporal-v1",
            }
        )
    virtual = SimpleNamespace(
        **{
            key: getattr(dataset, key)
            for key in ("id", "fingerprint", "size_bytes", "parsing_version", "pandas_version")
            if hasattr(dataset, key)
        },
        columns=columns,
    )
    return virtual, expanded, counts, errors


def resolved(ir, dataset, frame):
    if ir.temporal is None:
        return None
    from mlstudio.services.cleaning import temporal_config

    return ResolvedTemporalConfig(
        **temporal_config(ir).model_dump(mode="json"),
        input_dtypes={name: str(frame[name].dtype) for name in ir.temporal.sources},
    )


def features(ir, dataset, frame):
    from mlstudio.codegen.plan import operation
    from mlstudio.codegen.schemas import FeaturePlan

    if ir.temporal is not None or ir.derived is not None or ir.cleaning is not None:
        from mlstudio.services.derived import context as rowwise_context

        dataset, frame, _, _ = rowwise_context(ir, dataset, frame)
    if ir.imputation is not None:
        from mlstudio.services.imputation import context as imputation_context

        dataset, frame, _ = imputation_context(ir, dataset, frame)
    return tuple(
        FeaturePlan(
            name=c["name"],
            physical_dtype=str(frame[c["name"]].dtype),
            semantic_type=c["semantic_override"] or c["inferred_semantic_type"],
            operations=tuple(operation(op) for op in ir.features[c["name"]].operations)
            if c.get("inference_version") != "imputation-v1"
            else (),
        )
        for c in sorted(dataset.columns, key=lambda c: c["source_order"])
        if c.get("inference_version") == "imputation-v1"
        or (c["name"] in ir.features and ir.features[c["name"]].included)
    )


def warnings():
    return [
        "Confirm every datetime/reference is available at prediction time. "
        "Post-outcome timestamps can leak the target.",
        "Give fixed/per-row references an explicit prediction-time meaning; "
        "no current clock is substituted.",
        "Random splitting may be unsuitable for temporal data. Chronological evaluation "
        "is not implemented; the split is unchanged.",
    ]


def preview(session, project, settings, body):
    from sqlalchemy import select

    from mlstudio.models import Project
    from mlstudio.pipeline_schemas import load_ir
    from mlstudio.services.artifacts import verified_source
    from mlstudio.services.pipelines import snapshot
    from mlstudio.services.source import DomainError, json_scalar, parse_source

    project, dataset = snapshot(session, project.id)
    if project.revision != body.revision:
        raise DomainError("Project changed. Reload before previewing temporal features.", 409)
    ir = load_ir(body.ir.model_dump(mode="json"), project.ml_objective)
    if (
        dataset is None
        or ir.dataset is None
        or (ir.dataset.dataset_id != dataset.id or ir.dataset.fingerprint != dataset.fingerprint)
    ):
        raise DomainError("Reset preparation for the current Dataset before previewing.", 409)
    result = TemporalPreview(revision=body.revision)
    if (
        ir.temporal is not None
        or ir.derived is not None
        or ir.imputation is not None
        or ir.cleaning is not None
    ):
        frame = parse_source(verified_source(settings.home, dataset))
        try:
            from mlstudio.services.derived import context as rowwise_context

            raw_diagnostics = []
            if ir.cleaning is not None:
                from mlstudio.services.cleaning import evidence, raw_context

                cleaned_dataset, cleaned, raw_diagnostics = raw_context(
                    ir, dataset, frame, diagnostic=True
                )
                result.cleaning = CleaningPreview(
                    **evidence(cleaned_dataset, cleaned, len(frame), [], raw_diagnostics)
                )
            virtual, expanded, counts, errors = rowwise_context(ir, dataset, frame)
            if ir.cleaning is not None and not errors:
                from mlstudio.services.cleaning import selection

                expanded, events = selection(
                    ir, dataset, frame, virtual, expanded, validate_targets=False
                )
                result.cleaning = CleaningPreview(
                    **evidence(cleaned_dataset, expanded, len(frame), events, raw_diagnostics)
                )
            if ir.imputation is not None:
                from mlstudio.services.imputation import context as imputation_context

                virtual, expanded, diagnostics = imputation_context(ir, virtual, expanded)
                result.imputation = {
                    name: ImputationDiagnostics(**value) for name, value in diagnostics.items()
                }
            result.sources = {name: ParsingCounts(**value) for name, value in counts.items()}
            result.errors = errors
            result.warnings = (
                warnings()
                if ir.temporal is not None
                else [
                    "Confirm all expression inputs are available at prediction time; "
                    "semantic leakage is not automatically detected."
                ]
            )
            if ir.imputation is not None:
                result.warnings.append(
                    "Configuration preview only: no imputation statistics are fitted. "
                    "Predicate counts may overlap; missing groups and unknown conditions "
                    "do not guarantee a fill."
                )
            for c in virtual.columns[len(dataset.columns) :]:
                series = expanded[c["name"]]
                result.columns.append(
                    TemporalPreviewColumn(
                        name=c["name"],
                        semantic_type=c["inferred_semantic_type"],
                        missing_count=int(series.isna().sum()),
                        physical_dtype=str(series.dtype),
                        invalid_count=getattr(virtual, "derived_diagnostics", {})
                        .get(c["name"], {})
                        .get("invalid_count", 0),
                        values=[json_scalar(value) for value in series.head(result.limit)],
                    )
                )
        except (ValueError, KeyError, TypeError) as error:
            result.errors = [
                str(error)
                if isinstance(error, ValueError)
                else "Invalid temporal expression or source reference."
            ]
    if session.scalar(select(Project.revision).where(Project.id == project.id)) != body.revision:
        raise DomainError("Project changed during temporal preview. Reload.", 409)
    return result
