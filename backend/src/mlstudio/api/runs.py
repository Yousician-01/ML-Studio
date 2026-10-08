"""Backend Run acceptance and immutable historical inspection."""

from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from mlstudio.api.projects import CurrentProject, Database
from mlstudio.execution import service
from mlstudio.execution.process import WorkspaceLease
from mlstudio.execution.schemas import (
    ExecutionCapacity,
    HistoricalCode,
    RunList,
    RunRequest,
    RunResponse,
)
from mlstudio.models import Run
from mlstudio.services.source import DomainError

router = APIRouter(prefix="/projects/{project_id}/runs", tags=["runs"])


def owned_run(session, project_id, run_id):
    run = session.get(Run, run_id)
    if run is None or run.project_id != project_id:
        raise DomainError("Run not found.", 404)
    return run


@router.post("", response_model=RunResponse, status_code=202)
def create_run(body: RunRequest, project: CurrentProject, session: Database, request: Request):
    run = service.create(session, project.id, body, request.app.state.execution)
    return service.response(run, request.app.state.settings.home)


@router.get("", response_model=RunList)
def list_runs(
    project: CurrentProject,
    session: Database,
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    request_id: UUID | None = None,
):
    filters = [Run.project_id == project.id]
    if request_id is not None:
        filters.append(Run.request_id == str(request_id))
    runs = session.scalars(
        select(Run).where(*filters).order_by(Run.sequence.desc()).offset(offset).limit(limit)
    )
    return RunList(
        items=[service.response(run, request.app.state.settings.home) for run in runs],
        total=session.scalar(select(func.count()).select_from(Run).where(*filters)),
        offset=offset,
        limit=limit,
    )


@router.get("/capacity", response_model=ExecutionCapacity)
def capacity(project: CurrentProject, request: Request):
    coordinator = request.app.state.execution
    occupied = coordinator.guard.locked() or coordinator.blocked
    if not occupied:
        try:
            lease = WorkspaceLease(request.app.state.settings.home)
            lease.close()
        except (OSError, ValueError):
            occupied = True
    return ExecutionCapacity(occupied=occupied, recovery_required=coordinator.blocked)


@router.get("/{run_id}", response_model=RunResponse)
def get_run(run_id: str, project: CurrentProject, session: Database, request: Request):
    return service.response(
        owned_run(session, project.id, run_id), request.app.state.settings.home, detail=True
    )


@router.get("/{run_id}/code", response_model=HistoricalCode)
def get_code(run_id: str, project: CurrentProject, session: Database, request: Request):
    run = owned_run(session, project.id, run_id)
    return HistoricalCode(
        run_id=run.id,
        source=service.historical_source(run, request.app.state.settings.home),
        source_sha256=run.source_sha256,
    )
