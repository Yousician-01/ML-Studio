"""Project-owned text persistence, intentionally no execution routes."""

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from mlstudio.api.projects import CurrentProject, Database
from mlstudio.code_draft_schemas import (
    DraftCreate,
    DraftExit,
    DraftResponse,
    DraftSave,
    DraftSummary,
    ReportingProposal,
    SnapshotResponse,
    SnapshotSaved,
    SnapshotSummary,
)
from mlstudio.models import CodeDraft, CodeSnapshot
from mlstudio.services import code_drafts as service
from mlstudio.services.code_reporting import proposal

router = APIRouter(prefix="/projects/{project_id}/code-drafts", tags=["code drafts"])


@router.get("", response_model=list[DraftSummary])
def sessions(project: CurrentProject, session: Database, offset: int = Query(0, ge=0)):
    return (
        session.execute(
            select(
                CodeDraft.id,
                CodeDraft.status,
                CodeDraft.origin_revision,
                CodeDraft.created_at,
                CodeDraft.updated_at,
            )
            .where(CodeDraft.project_id == project.id)
            .order_by(CodeDraft.created_at.desc(), CodeDraft.id)
            .offset(offset)
            .limit(20)
        )
        .mappings()
        .all()
    )


@router.get("/active", response_model=DraftResponse | None)
def active(project: CurrentProject, session: Database):
    return service.response(service.active(session, project.id))


@router.post("", response_model=DraftResponse, status_code=201)
def create(body: DraftCreate, project: CurrentProject, session: Database, request: Request):
    return service.create(session, project, body, request.app.state.settings)


@router.get("/{draft_id}", response_model=DraftResponse)
def read(draft_id: str, project: CurrentProject, session: Database):
    return service.response(service.owned(session, project.id, draft_id))


@router.patch("/{draft_id}", response_model=DraftResponse)
def save(draft_id: str, body: DraftSave, project: CurrentProject, session: Database):
    return service.save(session, project.id, draft_id, body)


@router.post("/{draft_id}/reporting-proposal", response_model=ReportingProposal)
def reporting_proposal(draft_id: str, body: DraftSave, project: CurrentProject, session: Database):
    return proposal(session, project, draft_id, body)


@router.post("/{draft_id}/exit", response_model=DraftResponse)
def exit_session(draft_id: str, body: DraftExit, project: CurrentProject, session: Database):
    return service.exit_session(session, project, draft_id, body)


@router.post("/{draft_id}/snapshots", response_model=SnapshotSaved, status_code=201)
def save_snapshot(draft_id: str, body: DraftSave, project: CurrentProject, session: Database):
    return service.save(session, project.id, draft_id, body, snapshot=True)


@router.get("/{draft_id}/snapshots", response_model=list[SnapshotSummary])
def snapshots(
    draft_id: str, project: CurrentProject, session: Database, offset: int = Query(0, ge=0)
):
    service.owned(session, project.id, draft_id)
    return (
        session.execute(
            select(
                CodeSnapshot.id,
                CodeSnapshot.draft_id,
                CodeSnapshot.source_sha256,
                CodeSnapshot.created_at,
            )
            .where(CodeSnapshot.draft_id == draft_id)
            .order_by(CodeSnapshot.created_at.desc(), CodeSnapshot.id)
            .offset(offset)
            .limit(20)
        )
        .mappings()
        .all()
    )


@router.get("/{draft_id}/snapshots/{snapshot_id}", response_model=SnapshotResponse)
def snapshot(draft_id: str, snapshot_id: str, project: CurrentProject, session: Database):
    return service.snapshot(session, project.id, draft_id, snapshot_id)
