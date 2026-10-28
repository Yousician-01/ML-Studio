"""Local-only, opt-in manual Python execution and read-only captured output."""

from ipaddress import ip_address
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select, update

from mlstudio.api.projects import CurrentProject, Database
from mlstudio.code_run_schemas import (
    CodeEvaluationResponse,
    CodeRunRequest,
    CodeRunResponse,
    CodeRunStarted,
)
from mlstudio.execution.code_evaluation import evaluation
from mlstudio.execution.code_runs import ACTIVE, logs, owned, response
from mlstudio.models import CodeRun
from mlstudio.services.source import DomainError


def local_access(request: Request):
    settings = request.app.state.settings
    host = request.url.hostname
    client = request.client.host if request.client else ""
    testing = settings.environment == "test" and host == "testserver" and client == "testclient"
    try:
        local_client = ip_address(client).is_loopback
    except ValueError:
        local_client = False
    if not testing and (host not in {"localhost", "127.0.0.1", "::1"} or not local_client):
        raise DomainError("Code execution APIs require a loopback connection and local Host.", 403)
    origin = request.headers.get("origin")
    if origin and (
        origin not in settings.cors_origins
        or urlsplit(origin).hostname not in {"localhost", "127.0.0.1", "::1"}
    ):
        raise DomainError("Code execution origin is not permitted.", 403)


def enabled(request):
    if not request.app.state.settings.code_execution_enabled:
        raise DomainError(
            "Manual Python execution is disabled. Enable MLSTUDIO_CODE_EXECUTION_ENABLED "
            "for trusted local code only.",
            403,
        )


router = APIRouter(
    prefix="/projects/{project_id}/code-runs",
    tags=["code runs"],
    dependencies=[Depends(local_access)],
)


@router.post("", response_model=CodeRunStarted, status_code=202)
def start(body: CodeRunRequest, project: CurrentProject, session: Database, request: Request):
    enabled(request)
    return request.app.state.code_execution.start(session, project, body)


@router.get("")
def list_runs(
    project: CurrentProject, session: Database, request: Request, offset: int = Query(0, ge=0)
):
    condition = CodeRun.project_id == project.id
    rows = session.scalars(
        select(CodeRun)
        .where(condition)
        .order_by(CodeRun.created_at.desc(), CodeRun.id)
        .offset(offset)
        .limit(20)
    ).all()
    active = session.scalar(select(CodeRun).where(condition, CodeRun.status.in_(ACTIVE)))
    settings = request.app.state.settings
    return {
        "items": [response(settings, row, include_source=False) for row in rows],
        "total": session.scalar(select(func.count()).select_from(CodeRun).where(condition)),
        "active": response(settings, active, include_source=False) if active else None,
        "enabled": settings.code_execution_enabled,
    }


@router.get("/{run_id}", response_model=CodeRunResponse)
def detail(run_id: str, project: CurrentProject, session: Database, request: Request):
    return response(request.app.state.settings, owned(session, project.id, run_id))


@router.get("/{run_id}/logs")
def output(run_id: str, project: CurrentProject, session: Database, request: Request):
    return logs(request.app.state.settings, owned(session, project.id, run_id))


@router.get("/{run_id}/evaluation", response_model=CodeEvaluationResponse)
def results(run_id: str, project: CurrentProject, session: Database, request: Request):
    return evaluation(request.app.state.settings, owned(session, project.id, run_id))


@router.post("/{run_id}/cancel", response_model=CodeRunResponse)
def cancel(run_id: str, project: CurrentProject, session: Database, request: Request):
    enabled(request)
    row = owned(session, project.id, run_id)
    if row.status in ACTIVE:
        session.execute(
            update(CodeRun)
            .where(CodeRun.id == row.id, CodeRun.status.in_(ACTIVE))
            .values(cancel_requested=True),
            execution_options={"synchronize_session": False},
        )
        session.commit()
        session.refresh(row)
    return response(request.app.state.settings, row)
