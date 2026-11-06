"""Source-bound temporal validation and bounded preview; never persists raw rows."""

from types import SimpleNamespace

from pydantic import Field

from mlstudio.schemas import InputModel
from mlstudio.temporal_runtime_v1 import temporal_transform
from mlstudio.temporal_schemas import ResolvedTemporalConfig, validate_temporal


class TemporalPreviewColumn(InputModel):
    name: str
    semantic_type: str
    missing_count: int
    values: list[float | None]


class ParsingCounts(InputModel):
    missing_count: int
    invalid_count: int
    date_only_count: int


class TemporalPreview(InputModel):
    revision: int
    limit: int = 20
    columns: list[TemporalPreviewColumn] = Field(default_factory=list)
    sources: dict[str, ParsingCounts] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


def context(ir, dataset, frame):
    semantics = {
        c["name"]: c["semantic_override"] or c["inferred_semantic_type"] for c in dataset.columns
    }
    _, types = validate_temporal(ir.temporal, semantics, ir.target.column if ir.target else None)
    expanded, counts = temporal_transform(
        frame, ir.temporal.model_dump(mode="json"), diagnostic=True
    )
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
    return ResolvedTemporalConfig(
        **ir.temporal.model_dump(mode="json"),
        input_dtypes={name: str(frame[name].dtype) for name in ir.temporal.sources},
    )


def features(ir, dataset, frame):
    from mlstudio.codegen.plan import operation
    from mlstudio.codegen.schemas import FeaturePlan

    if ir.temporal is not None:
        dataset, frame, _, _ = context(ir, dataset, frame)
    return tuple(
        FeaturePlan(
            name=c["name"],
            physical_dtype=str(frame[c["name"]].dtype),
            semantic_type=c["semantic_override"] or c["inferred_semantic_type"],
            operations=tuple(operation(op) for op in ir.features[c["name"]].operations),
        )
        for c in sorted(dataset.columns, key=lambda c: c["source_order"])
        if c["name"] in ir.features and ir.features[c["name"]].included
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
    from mlstudio.services.source import DomainError, parse_source

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
    if ir.temporal is not None:
        frame = parse_source(verified_source(settings.home, dataset))
        try:
            virtual, expanded, counts, errors = context(ir, dataset, frame)
            result.sources = {name: ParsingCounts(**value) for name, value in counts.items()}
            result.errors = errors
            result.warnings = warnings()
            for c in virtual.columns[len(dataset.columns) :]:
                series = expanded[c["name"]]
                result.columns.append(
                    TemporalPreviewColumn(
                        name=c["name"],
                        semantic_type=c["inferred_semantic_type"],
                        missing_count=int(series.isna().sum()),
                        values=[
                            None if value != value else float(value)
                            for value in series.head(result.limit)
                        ],
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
