"""Persistent manual text; never compile, execute, or reverse-parse it."""

from copy import deepcopy
from hashlib import sha256

from pydantic import ValidationError
from sqlalchemy import select

from mlstudio.code_draft_schemas import DraftResponse, DraftSave
from mlstudio.code_runtime import code_mode_source
from mlstudio.models import CodeDraft, CodeSnapshot, Run, utc_now
from mlstudio.services.code_preview import preview
from mlstudio.services.source import DomainError


def active(session, project_id):
    return session.scalar(
        select(CodeDraft).where(CodeDraft.project_id == project_id, CodeDraft.status == "active")
    )


def require_visual_mode(session, project_id):
    if active(session, project_id):
        raise DomainError(
            "Code Mode is active. Save a code snapshot or explicitly discard the session "
            "before visual editing.",
            409,
        )


def owned(session, project_id, draft_id):
    draft = session.get(CodeDraft, draft_id)
    if draft is None or draft.project_id != project_id:
        raise DomainError("Code draft not found.", 404)
    return draft


def response(draft):
    if draft is None:
        return None
    return DraftResponse(
        **{name: getattr(draft, name) for name in DraftResponse.model_fields if name != "modified"},
        modified=draft.source != draft.baseline_source,
    )


def create(session, project, body, settings):
    require_visual_mode(session, project.id)
    generated = preview(session, project, settings)
    if (
        not generated.ready
        or generated.revision != body.revision
        or generated.source_sha256 != body.source_sha256
        or generated.plan_sha256 != body.plan_sha256
    ):
        raise DomainError(
            "Generated preview changed or is not ready. Refresh Code before entering Code Mode.",
            409,
        )
    source = code_mode_source(generated.source, project.ml_objective)
    try:
        DraftSave(revision=1, source=source)
    except ValidationError:
        raise DomainError("Generated source exceeds the 1 MiB Code Mode text limit.", 422) from None
    # Serialize with visual writes/admission. Their existing optimistic Project
    # guard rejects any race against this transition, preserving the originating IR.
    project.updated_at = utc_now()
    session.flush()
    if session.scalar(
        select(Run.id)
        .where(Run.project_id == project.id, Run.state.in_(("CREATED", "RUNNING")))
        .limit(1)
    ):
        raise DomainError("Wait for the active Run before entering Code Mode.", 409)
    draft = CodeDraft(
        project_id=project.id,
        origin_revision=generated.revision,
        origin_ir=deepcopy(project.working_pipeline),
        baseline_source=source,
        baseline_sha256="sha256:" + sha256(source.encode()).hexdigest(),
        plan_sha256=generated.plan_sha256,
        source=source,
    )
    session.add(draft)
    session.commit()
    return response(draft)


def writable(session, project_id, draft_id, revision):
    draft = owned(session, project_id, draft_id)
    if draft.status != "active" or draft.revision != revision:
        raise DomainError(
            "Code session changed. Reopen the saved draft before editing again; "
            "keep a copy of unsaved text.",
            409,
        )
    return draft


def save(session, project_id, draft_id, body, snapshot=False):
    draft = writable(session, project_id, draft_id, body.revision)
    draft.source, draft.updated_at = body.source, utc_now()
    frozen = add_snapshot(session, draft) if snapshot else None
    session.commit()
    return {"snapshot": frozen, "draft": response(draft)} if snapshot else response(draft)


def add_snapshot(session, draft):
    frozen = CodeSnapshot(
        draft_id=draft.id,
        source=draft.source,
        source_sha256="sha256:" + sha256(draft.source.encode()).hexdigest(),
    )
    session.add(frozen)
    return frozen


def exit_session(session, project, draft_id, body):
    from mlstudio.models import CodeRun

    draft = writable(session, project.id, draft_id, body.revision)
    project.updated_at = utc_now()
    session.flush()  # Shared serialization boundary with enter and visual writes.
    if session.scalar(
        select(CodeRun.id)
        .where(CodeRun.project_id == project.id, CodeRun.status.in_(("PENDING", "RUNNING")))
        .limit(1)
    ):
        raise DomainError("Stop or finish the Code Run before returning to visual editing.", 409)
    if body.action == "save_snapshot":
        draft.source = body.source
        add_snapshot(session, draft)
        draft.status = "archived"
    else:
        draft.source = draft.baseline_source
        draft.status = "discarded"
    draft.updated_at = utc_now()
    session.commit()
    return response(draft)


def snapshot(session, project_id, draft_id, snapshot_id):
    owned(session, project_id, draft_id)
    item = session.get(CodeSnapshot, snapshot_id)
    if item is None or item.draft_id != draft_id:
        raise DomainError("Code snapshot not found.", 404)
    return item
